"""Scientific acceptance coverage for technical-feasibility experiments."""

import csv
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from transcriptforge_analysis.technical_feasibility_experiment import (
    run_technical_feasibility_experiment,
    validate_technical_feasibility_design,
)

from demo.assay_development.generate_technical_feasibility_fixture import generate


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def test_technical_feasibility_bundle_is_deterministic_and_descriptive(
    tmp_path: Path,
) -> None:
    inputs = generate(tmp_path / "inputs")
    spec_path = Path(inputs["experiment_spec"])
    assignments_path = Path(inputs["experiment_assignments"])
    spec = json.loads(spec_path.read_text())
    design = validate_technical_feasibility_design(spec, _rows(assignments_path))
    assert design.valid
    assert design.specimen_groups == ["FFPE", "fresh_frozen"]

    manifests = [
        run_technical_feasibility_experiment(
            spec_path,
            assignments_path,
            Path(inputs["expression_bundle"]),
            tmp_path / output,
        )
        for output in ("first", "second")
    ]
    assert manifests[0] == manifests[1]
    repository = Path(__file__).parents[3]
    Draft202012Validator(
        json.loads(
            (repository / "contracts/experiment/experiment_spec.schema.json").read_text()
        )
    ).validate(spec)
    Draft202012Validator(
        json.loads(
            (
                repository
                / "contracts/experiment/development_evidence_manifest.schema.json"
            ).read_text()
        )
    ).validate(manifests[0])
    root = tmp_path / "first/development_evidence_bundle"
    primary = json.loads((root / "results/primary_results.json").read_text())
    summary = json.loads((root / "decision/decision_summary.json").read_text())
    assert primary["overall_summary"]["technical_success_rate"] == 0.875
    assert primary["overall_summary"]["successful_measurements"] == 7
    assert primary["failure_association_review"]["specimen_group"][0]["group"] == "FFPE"
    assert summary["scientist_decision_required"] is True
    assert summary["criteria_mode"] == "exploratory"
    model_summary = json.loads((root / "results/model_summaries.json").read_text())
    assert model_summary["models"] == []


def test_technical_feasibility_blocks_missing_run_and_small_design(tmp_path: Path) -> None:
    inputs = generate(tmp_path / "inputs")
    spec = json.loads(Path(inputs["experiment_spec"]).read_text())
    rows = _rows(Path(inputs["experiment_assignments"]))[:2]
    rows[0]["run"] = ""
    design = validate_technical_feasibility_design(spec, rows)
    codes = {item.code for item in design.findings}
    assert not design.valid
    assert "ASSIGNMENT.FEASIBILITY_METADATA_REQUIRED" in codes
    assert "DESIGN.FEASIBILITY_SAMPLE_COUNT" in codes
