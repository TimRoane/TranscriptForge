"""Large demonstration dataset reproducibility tests."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]


def _generator() -> ModuleType:
    path = ROOT / "demo/large_experiment/generate.py"
    specification = importlib.util.spec_from_file_location("large_demo_generator", path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_large_demo_generator_is_deterministic_and_balanced(tmp_path: Path) -> None:
    generator = _generator()
    first = tmp_path / "first"
    second = tmp_path / "second"

    summary = generator.generate(first)
    generator.generate(second)

    assert summary["sample_count"] == 72
    assert summary["subject_count"] == 36
    assert summary["groups"] == {
        "wild_type_vehicle": 18,
        "wild_type_stimulated": 18,
        "variant_vehicle": 18,
        "variant_stimulated": 18,
    }
    for filename in (
        "counts.tsv",
        "sample_metadata.tsv",
        "ground_truth.tsv",
        "experiment_summary.json",
    ):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()
    persisted = json.loads((first / "experiment_summary.json").read_text())
    assert persisted["feature_count"] == 2_000
