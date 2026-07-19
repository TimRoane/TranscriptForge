"""Acceptance coverage for paired robustness/interference studies."""

import json
from pathlib import Path

import pytest
from transcriptforge_analysis.robustness_interference_study import (
    run_robustness_interference_study,
)

from demo.assay_development.generate_robustness_fixture import generate


def test_robustness_study_is_deterministic_and_never_retrains(tmp_path: Path) -> None:
    inputs = generate(tmp_path / "inputs")
    before = Path(inputs["model"]).read_bytes()
    runs = []
    for name in ("first", "second"):
        runs.append(
            run_robustness_interference_study(
                Path(inputs["expression_bundle"]),
                Path(inputs["model"]),
                Path(inputs["model_manifest"]),
                Path(inputs["study_spec"]),
                Path(inputs["study_assignments"]),
                tmp_path / name,
            )
        )
    assert runs[0] == runs[1]
    assert Path(inputs["model"]).read_bytes() == before
    assert runs[0]["overall_status"] == "PASS"
    metrics = runs[0]["metrics"]
    assert abs(metrics["mean_challenge_effect"]) < 0.05
    assert metrics["call_change_rate"] == 0
    assert metrics["qc_failure_rate"] == 0
    assert metrics["biological_specificity_claims_supported"] is False
    assert len(metrics["challenge_type_review"]) == 1
    assert (tmp_path / "first/validation_bundle/figures/challenge_effect_plot.svg").is_file()


def test_runner_rejects_unsupported_specificity_claim_policy(tmp_path: Path) -> None:
    inputs = generate(tmp_path / "inputs")
    spec = Path(inputs["study_spec"])
    payload = json.loads(spec.read_text())
    payload["analysis_plan"]["biological_specificity_claims_supported"] = True
    spec.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="biological-specificity"):
        run_robustness_interference_study(
            Path(inputs["expression_bundle"]),
            Path(inputs["model"]),
            Path(inputs["model_manifest"]),
            spec,
            Path(inputs["study_assignments"]),
            tmp_path / "result",
        )
