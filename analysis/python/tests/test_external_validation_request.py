"""Frozen biological classifier request tests."""

import csv
import json
from pathlib import Path

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from demo.classifier_external_validation.freeze_development_request import freeze_request

ROOT = Path(__file__).parents[3]


def test_development_request_freezes_grouped_repeated_nested_cv(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata.tsv"
    with metadata.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(("sample_id", "response", "patient_id"))
        for index in range(25):
            writer.writerow((f"positive_{index}", "pCR", f"positive_{index}"))
        for index in range(70):
            writer.writerow((f"negative_{index}", "nCR", f"negative_{index}"))
    output = tmp_path / "request.json"
    request = freeze_request(metadata, output)
    Draft202012Validator(
        json.loads((ROOT / "schemas/analysis_request.schema.json").read_text())
    ).validate(request)
    assert request["parameters"]["permutation_count"] == 100  # type: ignore[index]
    validation = request["design_validation"]  # type: ignore[assignment]
    assert len(validation["fold_plan"]) == 25  # type: ignore[index]
    assert all(item["group_overlap_count"] == 0 for item in validation["fold_plan"])  # type: ignore[index]
