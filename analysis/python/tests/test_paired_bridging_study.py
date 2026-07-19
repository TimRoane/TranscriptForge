"""Acceptance coverage for locked-model paired bridging studies."""

import json
from pathlib import Path

from transcriptforge_analysis.paired_bridging_study import run_paired_bridging_study

from demo.assay_development.generate_paired_bridge_fixture import generate


def test_paired_bridge_is_deterministic_and_uses_multiple_equivalence_metrics(
    tmp_path: Path,
) -> None:
    inputs = generate(tmp_path / "inputs")
    model_before = Path(inputs["model"]).read_bytes()
    first = run_paired_bridging_study(
        Path(inputs["expression_bundle"]),
        Path(inputs["model"]),
        Path(inputs["model_manifest"]),
        Path(inputs["study_spec"]),
        Path(inputs["study_assignments"]),
        tmp_path / "first",
    )
    second = run_paired_bridging_study(
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
    metrics = first["metrics"]
    assert abs(metrics["paired_bias"]) < 0.05
    assert metrics["categorical_agreement"] == 1
    assert metrics["tost_equivalence"]["passed"] is True
    assert metrics["correlation_passes_equivalence"] is False
    assert metrics["deming_regression"]["status"] == "ESTIMATED"
    assert len(metrics["subgroup_review"]) == 2
    for relative in (
        "manifest.json",
        "metrics/paired_bridging_metrics.json",
        "metrics/acceptance_results.json",
        "figures/paired_bridge_bland_altman.svg",
        "decision/decision_summary.json",
    ):
        assert (
            tmp_path / "first/validation_bundle" / relative
        ).read_bytes() == (tmp_path / "second/validation_bundle" / relative).read_bytes()


def test_correlation_only_cannot_pass_equivalence(tmp_path: Path) -> None:
    inputs = generate(tmp_path / "inputs")
    spec_path = Path(inputs["study_spec"])
    spec = json.loads(spec_path.read_text())
    spec["acceptance_criteria"] = [
        {
            "key": "correlation_only",
            "metric": "profile_correlation",
            "endpoint": "classifier_score",
            "operator": "gte",
            "threshold": 0.99,
            "rationale": "Deliberate negative-control criterion.",
        }
    ]
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    result = run_paired_bridging_study(
        Path(inputs["expression_bundle"]),
        Path(inputs["model"]),
        Path(inputs["model_manifest"]),
        spec_path,
        Path(inputs["study_assignments"]),
        tmp_path / "result",
    )
    assert result["overall_status"] == "INDETERMINATE"
    assert result["acceptance_results"][0]["status"] == "NOT_APPLICABLE"
