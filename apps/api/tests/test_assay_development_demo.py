"""Reproducibility and teaching-state checks for the synthetic FFPE demo."""

import csv
from pathlib import Path

from transcriptforge_analysis.assay_experiment import validate_input_degradation_design

from demo.assay_development.generate import generate


def test_synthetic_ffpe_demo_is_deterministic_and_deliberately_repairable(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert generate(first) == generate(second)
    for name in ("counts.tsv", "sample_metadata.tsv", "study_summary.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()

    with (first / "sample_metadata.tsv").open(encoding="utf-8", newline="") as source:
        metadata = list(csv.DictReader(source, delimiter="\t"))
    assignments = [
        {
            "measurement_id": row["sample_id"],
            "biological_sample_id": row["biological_sample_id"],
            "prepared_dataset_id": "prepared-demo",
            "include": "true",
            "exclusion_reason": "",
            "replicate_id": row["input_ng"],
            "input_ng": row["input_ng"],
            "dv200": row["dv200"],
            "sequencing_run": f"run_input_{row['input_ng']}",
        }
        for row in metadata
    ]
    spec = {
        "experiment": {
            "type": "INPUT_DEGRADATION_EXPLORATION",
            "mode": "ANALYZE_EXISTING",
        },
        "analysis_plan": {"reference_level": 100},
    }
    blocked = validate_input_degradation_design(spec, assignments)
    assert blocked.valid is False
    assert "DESIGN.INPUT_RUN_CONFOUNDED" in {item.code for item in blocked.findings}

    for assignment, row in zip(assignments, metadata, strict=True):
        assignment["sequencing_run"] = row["sequencing_run"]
    repaired = validate_input_degradation_design(spec, assignments)
    assert repaired.valid is True
