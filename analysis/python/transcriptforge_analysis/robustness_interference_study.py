"""Locked-model paired robustness and interference Analytical Study."""

from __future__ import annotations

import json
import math
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from transcriptforge_analysis.classifier_prediction import predict_with_model
from transcriptforge_analysis.matrix_validation import write_json_atomic
from transcriptforge_analysis.paired_bridging_study import (
    _criterion_status,
    _write_bland_altman,
)
from transcriptforge_analysis.precision_study import (
    CONTRACT_ROOT,
    _archive,
    _boolean,
    _confounding,
    _factor_balance,
    _manifest,
    _pdf,
    _provenance,
    _read_tsv,
    _sha,
    _write_endpoint_tables,
    _write_tsv,
)


def run_robustness_interference_study(
    bundle: Path,
    model: Path,
    model_manifest: Path,
    study_spec: Path,
    assignments_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Apply one frozen model and quantify paired challenge effects."""
    spec = json.loads(study_spec.read_text(encoding="utf-8"))
    _validate_spec(spec, model_manifest)
    assignments = _read_tsv(assignments_path)
    _validate_assignments(assignments, spec)
    output_dir.mkdir(parents=True, exist_ok=False)
    prediction_dir = output_dir / "_locked_prediction"
    prediction = predict_with_model(bundle, model, prediction_dir, model_manifest)
    prediction_by_id = {row["sample_id"]: row for row in prediction["predictions"]}
    included = [row for row in assignments if _boolean(row.get("include", "true"))]
    if {row["measurement_id"] for row in included} != set(prediction_by_id):
        raise ValueError("Study assignments must map every prediction sample exactly once.")
    endpoints: list[dict[str, Any]] = []
    for row in included:
        predicted = prediction_by_id[row["measurement_id"]]
        score = (
            float(predicted["positive_probability"])
            if "positive_probability" in predicted
            else float(max(predicted["class_probabilities"].values()))
        )
        endpoints.append(
            {**row, "classifier_score": score, "predicted_class": predicted["predicted_class"]}
        )
    plan = spec["analysis_plan"]
    reference_name = str(plan["reference_condition"])
    challenge_name = str(plan["challenge_condition"])
    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in endpoints:
        grouped[row["biological_sample_id"]][row["condition"]] = row
    pairs: list[dict[str, Any]] = []
    for sample_id in sorted(grouped):
        reference = grouped[sample_id][reference_name]
        challenge = grouped[sample_id][challenge_name]
        pairs.append(
            {
                "biological_sample_id": sample_id,
                "reference_measurement_id": reference["measurement_id"],
                "challenge_measurement_id": challenge["measurement_id"],
                "challenge_type": challenge.get("challenge_type")
                or reference.get("challenge_type"),
                "subgroup": challenge.get("subgroup") or reference.get("subgroup") or "",
                "reference_score": reference["classifier_score"],
                "challenge_score": challenge["classifier_score"],
                "challenge_effect": challenge["classifier_score"] - reference["classifier_score"],
                "pair_average_score": (
                    challenge["classifier_score"] + reference["classifier_score"]
                )
                / 2,
                "paired_bias": challenge["classifier_score"] - reference["classifier_score"],
                "reference_call": reference["predicted_class"],
                "challenge_call": challenge["predicted_class"],
                "call_changed": reference["predicted_class"] != challenge["predicted_class"],
                "qc_failure": _boolean(challenge.get("qc_failure", "false")),
            }
        )
    metrics = _metrics(
        pairs,
        float(plan["maximum_effect_margin"]),
        float(plan["threshold_proximity_band"]),
        float(prediction.get("decision_threshold", 0.5)),
    )
    criteria = _evaluate_criteria(spec["acceptance_criteria"], metrics)
    overall = (
        "FAIL"
        if any(item["status"] == "FAIL" for item in criteria)
        else "INDETERMINATE"
        if any(item["status"] in {"INDETERMINATE", "NOT_APPLICABLE"} for item in criteria)
        else "PASS"
    )
    root = output_dir / "validation_bundle"
    _write_bundle(
        root,
        spec,
        assignments,
        endpoints,
        pairs,
        metrics,
        criteria,
        overall,
        model_manifest,
        bundle,
        model,
    )
    write_json_atomic(root / "manifest.json", _manifest(root, spec, overall))
    archive = output_dir / "validation_bundle.tar.gz"
    _archive(root, archive)
    shutil.rmtree(prediction_dir)
    return {
        "study_id": spec["study"]["study_id"],
        "overall_status": overall,
        "metrics": metrics,
        "acceptance_results": criteria,
        "bundle_sha256": _sha(archive),
    }


def _validate_spec(spec: dict[str, Any], manifest_path: Path) -> None:
    schema = json.loads((CONTRACT_ROOT / "study_spec.schema.json").read_text())
    errors = sorted(
        Draft202012Validator(schema).iter_errors(spec), key=lambda item: list(item.path)
    )
    if errors:
        location = ".".join(str(value) for value in errors[0].path) or "document"
        raise ValueError(f"StudySpec violates its contract at {location}: {errors[0].message}")
    if spec["study"]["type"] != "ROBUSTNESS_INTERFERENCE":
        raise ValueError("The challenge runner requires ROBUSTNESS_INTERFERENCE.")
    if spec["model"]["manifest_sha256"] != _sha(manifest_path):
        raise ValueError("StudySpec model manifest checksum does not match the locked input.")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("model_id") != spec["model"]["model_id"]:
        raise ValueError("StudySpec model identity does not match the locked ModelManifest.")
    if spec["analysis_plan"].get("biological_specificity_claims_supported") is not False:
        raise ValueError(
            "This template cannot be configured to make biological-specificity claims."
        )


def _validate_assignments(rows: list[dict[str, str]], spec: dict[str, Any]) -> None:
    required = {
        "measurement_id",
        "biological_sample_id",
        "condition",
        "challenge_type",
        "run",
        "include",
    }
    if not rows or required - set(rows[0]):
        raise ValueError("Robustness/interference assignments lack required columns.")
    identifiers = [row["measurement_id"] for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Study measurement identifiers must be unique.")
    plan = spec["analysis_plan"]
    expected = sorted([str(plan["reference_condition"]), str(plan["challenge_condition"])])
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if _boolean(row["include"]):
            grouped[row["biological_sample_id"]].append(row["condition"])
    if len(grouped) < 4 or any(sorted(values) != expected for values in grouped.values()):
        raise ValueError("Every sample requires exactly one reference and challenge measurement.")


def _metrics(
    pairs: list[dict[str, Any]], margin: float, proximity_band: float, threshold: float
) -> dict[str, Any]:
    effects = np.asarray([row["challenge_effect"] for row in pairs], dtype=float)
    mean = float(np.mean(effects))
    sd = float(np.std(effects, ddof=1))
    interval = {
        "lower": mean - 1.96 * sd / math.sqrt(len(effects)),
        "upper": mean + 1.96 * sd / math.sqrt(len(effects)),
    }
    per_type = []
    for challenge_type in sorted({str(row["challenge_type"]) for row in pairs}):
        selected = [row for row in pairs if row["challenge_type"] == challenge_type]
        per_type.append(
            {
                "challenge_type": challenge_type,
                "pair_count": len(selected),
                "mean_challenge_effect": float(
                    np.mean([row["challenge_effect"] for row in selected])
                ),
                "call_change_rate": float(np.mean([row["call_changed"] for row in selected])),
                "qc_failure_rate": float(np.mean([row["qc_failure"] for row in selected])),
            }
        )
    near = [
        row
        for row in pairs
        if min(
            abs(float(row["reference_score"]) - threshold),
            abs(float(row["challenge_score"]) - threshold),
        )
        <= proximity_band
    ]
    return {
        "pair_count": len(pairs),
        "mean_challenge_effect": mean,
        "challenge_effect_sd": sd,
        "challenge_effect_confidence_interval_95": interval,
        "maximum_effect_margin": margin,
        "effect_within_margin": interval["lower"] > -margin and interval["upper"] < margin,
        "call_change_rate": float(np.mean([row["call_changed"] for row in pairs])),
        "qc_failure_rate": float(np.mean([row["qc_failure"] for row in pairs])),
        "challenge_type_review": per_type,
        "threshold_adjacent_review": {
            "decision_threshold": threshold,
            "proximity_band": proximity_band,
            "pair_count": len(near),
            "pairs": near,
        },
        "biological_specificity_claims_supported": False,
    }


def _evaluate_criteria(
    criteria: list[dict[str, Any]], metrics: dict[str, Any]
) -> list[dict[str, Any]]:
    endpoints = {
        "mean_challenge_effect": "classifier_score",
        "call_change_rate": "predicted_class",
        "qc_failure_rate": "qc_failure",
    }
    results = []
    for criterion in criteria:
        observed = metrics.get(criterion["metric"])
        if observed is None or criterion["endpoint"] != endpoints.get(criterion["metric"]):
            status, note = "NOT_APPLICABLE", "Metric/endpoint combination is unsupported."
        else:
            status = _criterion_status(
                float(observed), criterion["operator"], float(criterion["threshold"])
            )
            note = None
        results.append(
            {
                **criterion,
                "observed": observed,
                "status": status,
                "population": "all included complete challenge/reference pairs",
                "uncertainty": metrics["challenge_effect_confidence_interval_95"]
                if criterion["metric"] == "mean_challenge_effect"
                else None,
                "note": note,
            }
        )
    return results


def _write_bundle(
    root: Path,
    spec: dict[str, Any],
    assignments: list[dict[str, str]],
    endpoints: list[dict[str, Any]],
    pairs: list[dict[str, Any]],
    metrics: dict[str, Any],
    criteria: list[dict[str, Any]],
    overall: str,
    model_manifest: Path,
    expression_bundle: Path,
    model: Path,
) -> None:
    for directory in (
        "design",
        "endpoints",
        "metrics",
        "figures",
        "decision",
        "provenance/nextflow_metadata",
        "report",
    ):
        (root / directory).mkdir(parents=True, exist_ok=True)
    (root / "study_spec.yaml").write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    shutil.copyfile(model_manifest, root / "model_manifest.json")
    _write_tsv(root / "design/study_assignments.tsv", assignments)
    write_json_atomic(root / "design/design_validation.json", spec["design_validation"])
    _factor_balance(root / "design/factor_balance.tsv", endpoints, spec["factors"])
    _confounding(root / "design/confounding_matrix.tsv", endpoints, spec["factors"])
    _write_endpoint_tables(root / "endpoints", endpoints)
    _write_tsv(root / "endpoints/challenge_pair_results.tsv", pairs)
    _write_tsv(
        root / "endpoints/excluded_measurements.tsv",
        [row for row in assignments if not _boolean(row.get("include", "true"))],
    )
    write_json_atomic(root / "metrics/robustness_interference_metrics.json", metrics)
    write_json_atomic(
        root / "metrics/acceptance_results.json", {"overall_status": overall, "criteria": criteria}
    )
    write_json_atomic(
        root / "metrics/threshold_stability.json", metrics["threshold_adjacent_review"]
    )
    summary = {
        "study_id": spec["study"]["study_id"],
        "question": spec["study"]["objective"],
        "overall_status": overall,
        "finding": f"Prespecified challenge criteria resolved to {overall}.",
        "criteria": criteria,
        "limitations": [
            "Challenge effects do not establish biological specificity.",
            "Only prespecified tested challenges are represented.",
            "The locked model was applied without retraining.",
        ],
        "scientist_decision_required": True,
    }
    write_json_atomic(root / "decision/decision_summary.json", summary)
    (root / "decision/decision_summary.md").write_text(
        "# Robustness/interference decision summary\n\n"
        f"**Overall:** {overall}\n\n{summary['finding']}\n"
    )
    write_json_atomic(
        root / "decision/recommendations.json",
        {"recommendations": [{"action": "SCIENTIST_REVIEW", "launch_automatically": False}]},
    )
    write_json_atomic(
        root / "decision/unresolved_questions.json", {"questions": summary["limitations"]}
    )
    _write_bland_altman(
        root / "figures/challenge_effect_plot.svg",
        pairs,
        {
            "bland_altman_limits_of_agreement": {
                "lower": metrics["mean_challenge_effect"] - 1.96 * metrics["challenge_effect_sd"],
                "upper": metrics["mean_challenge_effect"] + 1.96 * metrics["challenge_effect_sd"],
            },
            "paired_bias": metrics["mean_challenge_effect"],
        },
    )
    _provenance(root / "provenance", expression_bundle, model, model_manifest, spec)
    root.joinpath("report/validation_report.html").write_text(
        "<!doctype html><html><body><h1>Robustness and interference study</h1>"
        f"<h2>{spec['study']['name']}</h2><p>Overall: <strong>{overall}</strong></p>"
        f"<p>Mean challenge effect: {metrics['mean_challenge_effect']:.4f}; "
        f"call-change rate: {metrics['call_change_rate']:.3f}.</p>"
        "<p>No biological-specificity claim is supported. Locked model applied without "
        "retraining. Scientist decision required.</p></body></html>\n"
    )
    _pdf(
        root / "report/validation_report.pdf",
        [
            "TranscriptForge Robustness and Interference Study",
            spec["study"]["name"],
            f"Overall: {overall}",
            f"Mean challenge effect: {metrics['mean_challenge_effect']:.4f}",
            "No biological-specificity claim is supported.",
            "Locked model applied without retraining.",
        ],
    )
