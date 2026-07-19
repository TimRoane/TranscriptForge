"""Acceptance coverage for locked-model input/degradation limit studies."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from transcriptforge_analysis.input_degradation_study import (
    run_input_degradation_limit_study,
)

from demo.assay_development.generate_input_limit_fixture import generate


def test_input_limit_study_is_deterministic_and_reports_consecutive_candidate(
    tmp_path: Path,
) -> None:
    inputs = generate(tmp_path / "inputs")
    model_before = Path(inputs["model"]).read_bytes()
    first = run_input_degradation_limit_study(
        Path(inputs["expression_bundle"]),
        Path(inputs["model"]),
        Path(inputs["model_manifest"]),
        Path(inputs["study_spec"]),
        Path(inputs["study_assignments"]),
        tmp_path / "first",
    )
    second = run_input_degradation_limit_study(
        Path(inputs["expression_bundle"]),
        Path(inputs["model"]),
        Path(inputs["model_manifest"]),
        Path(inputs["study_spec"]),
        Path(inputs["study_assignments"]),
        tmp_path / "second",
    )
    assert first == second
    assert Path(inputs["model"]).read_bytes() == model_before
    assert first["overall_status"] == "PASS"
    assert first["metrics"]["candidate_lowest_tested_level"] == 25
    assert {item["status"] for item in first["acceptance_results"]} == {"PASS"}
    for relative in (
        "manifest.json",
        "metrics/input_degradation_metrics.json",
        "metrics/acceptance_results.json",
        "decision/decision_summary.json",
        "figures/score_stability_by_level.svg",
        "report/validation_report.html",
    ):
        assert (
            tmp_path / "first/validation_bundle" / relative
        ).read_bytes() == (tmp_path / "second/validation_bundle" / relative).read_bytes()
    manifest = json.loads(
        (tmp_path / "first/validation_bundle/manifest.json").read_text()
    )
    schema = json.loads(
        (
            Path(__file__).parents[3]
            / "contracts/validation/validation_bundle_manifest.schema.json"
        ).read_text()
    )
    Draft202012Validator(schema).validate(manifest)


def test_input_limit_study_rejects_incomplete_pairs(tmp_path: Path) -> None:
    inputs = generate(tmp_path / "inputs")
    assignment_path = Path(inputs["study_assignments"])
    lines = assignment_path.read_text().splitlines()
    assignment_path.write_text("\n".join(lines[:-1]) + "\n")
    try:
        run_input_degradation_limit_study(
            Path(inputs["expression_bundle"]),
            Path(inputs["model"]),
            Path(inputs["model_manifest"]),
            Path(inputs["study_spec"]),
            assignment_path,
            tmp_path / "result",
        )
    except ValueError as error:
        assert "exactly one measurement at each level" in str(error)
    else:
        raise AssertionError("Incomplete paired levels were not rejected.")
