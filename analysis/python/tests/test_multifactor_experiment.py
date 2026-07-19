"""Acceptance coverage for constrained multifactor optimization."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from transcriptforge_analysis.multifactor_experiment import (
    run_multifactor_experiment,
    validate_multifactor_design,
)

from demo.assay_development.generate_multifactor_fixture import generate


def _rows(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def test_multifactor_runner_is_deterministic_and_bounded(tmp_path: Path) -> None:
    inputs = generate(tmp_path / "inputs")
    spec = json.loads(Path(inputs["experiment_spec"]).read_text())
    design = validate_multifactor_design(spec, _rows(Path(inputs["experiment_assignments"])))
    assert design.valid
    repository = Path(__file__).parents[3]
    Draft202012Validator(
        json.loads(
            (repository / "contracts/experiment/experiment_spec.schema.json").read_text()
        )
    ).validate(spec)
    outputs = []
    for name in ("first", "second"):
        outputs.append(
            run_multifactor_experiment(
                Path(inputs["experiment_spec"]),
                Path(inputs["experiment_assignments"]),
                Path(inputs["expression_bundle"]),
                tmp_path / name,
            )
        )
    assert outputs[0] == outputs[1]
    primary = json.loads(
        (tmp_path / "first/development_evidence_bundle/results/primary_results.json").read_text()
    )
    assert primary["experiment_type"] == "MULTIFACTOR_OPTIMIZATION"
    assert (
        primary["variance_decomposition"]["repeated_sample_method"]
        == "biological_sample_fixed_block"
    )
    assert primary["response_surface"]["status"] == "NOT_SUPPORTED"
    assert any("extraction_method" in row["term"] for row in primary["fixed_effect_estimates"])


def test_sparse_multifactor_design_is_blocked(tmp_path: Path) -> None:
    inputs = generate(tmp_path / "inputs")
    spec = json.loads(Path(inputs["experiment_spec"]).read_text())
    rows = _rows(Path(inputs["experiment_assignments"]))[:8]
    design = validate_multifactor_design(spec, rows)
    assert not design.valid
    assert "DESIGN.MULTIFACTOR_TOO_SPARSE" in {item.code for item in design.findings}
