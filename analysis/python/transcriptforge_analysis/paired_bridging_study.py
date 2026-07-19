"""Locked-model paired bridging Analytical Study."""

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


def run_paired_bridging_study(
    bundle: Path,
    model: Path,
    model_manifest: Path,
    study_spec: Path,
    assignments_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Apply a locked model once and evaluate a paired reference/comparator bridge."""
    spec = json.loads(study_spec.read_text(encoding="utf-8"))
    _validate_spec(spec, model_manifest)
    assignments = _read_tsv(assignments_path)
    _validate_assignments(assignments, spec)
    output_dir.mkdir(parents=True, exist_ok=False)
    prediction_dir = output_dir / "_locked_prediction"
    prediction = predict_with_model(bundle, model, prediction_dir, model_manifest)
    prediction_by_sample = {row["sample_id"]: row for row in prediction["predictions"]}
    included = [row for row in assignments if _boolean(row.get("include", "true"))]
    if {row["measurement_id"] for row in included} != set(prediction_by_sample):
        raise ValueError("Study assignments must map every prediction sample exactly once.")
    measurements = []
    for row in included:
        predicted = prediction_by_sample[row["measurement_id"]]
        score = (
            float(predicted["positive_probability"])
            if "positive_probability" in predicted
            else float(max(predicted["class_probabilities"].values()))
        )
        measurements.append(
            {**row, "classifier_score": score, "predicted_class": predicted["predicted_class"]}
        )
    plan = spec["analysis_plan"]
    reference_condition = str(plan["reference_condition"])
    comparator_condition = str(plan["comparator_condition"])
    by_sample: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in measurements:
        by_sample[row["biological_sample_id"]][row["condition"]] = row
    pairs = []
    for sample_id in sorted(by_sample):
        reference = by_sample[sample_id][reference_condition]
        comparator = by_sample[sample_id][comparator_condition]
        pairs.append(
            {
                "biological_sample_id": sample_id,
                "reference_measurement_id": reference["measurement_id"],
                "comparator_measurement_id": comparator["measurement_id"],
                "reference_condition": reference_condition,
                "comparator_condition": comparator_condition,
                "reference_score": reference["classifier_score"],
                "comparator_score": comparator["classifier_score"],
                "paired_bias": comparator["classifier_score"] - reference["classifier_score"],
                "pair_average_score": (
                    comparator["classifier_score"] + reference["classifier_score"]
                )
                / 2,
                "reference_call": reference["predicted_class"],
                "comparator_call": comparator["predicted_class"],
                "call_agreement": reference["predicted_class"]
                == comparator["predicted_class"],
                "discordant": reference["predicted_class"] != comparator["predicted_class"],
                "subgroup": comparator.get("subgroup") or reference.get("subgroup") or "",
            }
        )
    metrics = _bridge_metrics(
        pairs,
        float(plan["equivalence_margin"]),
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
    bundle_dir = output_dir / "validation_bundle"
    _write_bundle(
        bundle_dir,
        spec,
        assignments,
        measurements,
        pairs,
        metrics,
        criteria,
        overall,
        model_manifest,
        bundle,
        model,
    )
    manifest = _manifest(bundle_dir, spec, overall)
    write_json_atomic(bundle_dir / "manifest.json", manifest)
    archive = output_dir / "validation_bundle.tar.gz"
    _archive(bundle_dir, archive)
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
        Draft202012Validator(schema).iter_errors(spec), key=lambda error: list(error.path)
    )
    if errors:
        location = ".".join(str(value) for value in errors[0].path) or "document"
        raise ValueError(f"StudySpec violates its contract at {location}: {errors[0].message}")
    if spec["study"]["type"] != "PAIRED_BRIDGING":
        raise ValueError("The paired bridge runner requires PAIRED_BRIDGING.")
    if spec["model"]["manifest_sha256"] != _sha(manifest_path):
        raise ValueError("StudySpec model manifest checksum does not match the locked input.")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("model_id") != spec["model"]["model_id"]:
        raise ValueError("StudySpec model identity does not match the locked ModelManifest.")
    if spec["analysis_plan"].get("correlation_passes_equivalence") is not False:
        raise ValueError("Correlation must never be configured to pass equivalence.")


def _validate_assignments(rows: list[dict[str, str]], spec: dict[str, Any]) -> None:
    required = {"measurement_id", "biological_sample_id", "condition", "run", "include"}
    if not rows or required - set(rows[0]):
        raise ValueError("Paired bridge assignments lack required columns.")
    identifiers = [row["measurement_id"] for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Study measurement identifiers must be unique.")
    included = [row for row in rows if _boolean(row["include"])]
    reference = str(spec["analysis_plan"]["reference_condition"])
    comparator = str(spec["analysis_plan"]["comparator_condition"])
    by_sample: dict[str, list[str]] = defaultdict(list)
    for row in included:
        by_sample[row["biological_sample_id"]].append(row["condition"])
    if len(by_sample) < 4 or any(
        sorted(values) != sorted([reference, comparator]) for values in by_sample.values()
    ):
        raise ValueError("Every bridge sample requires exactly one reference and comparator.")


def _bridge_metrics(
    pairs: list[dict[str, Any]], margin: float, proximity_band: float, threshold: float
) -> dict[str, Any]:
    reference = np.asarray([row["reference_score"] for row in pairs], dtype=float)
    comparator = np.asarray([row["comparator_score"] for row in pairs], dtype=float)
    differences = comparator - reference
    bias = float(np.mean(differences))
    sd = float(np.std(differences, ddof=1))
    se = sd / math.sqrt(len(differences))
    ci = {"lower": bias - 1.96 * se, "upper": bias + 1.96 * se}
    correlation = (
        float(np.corrcoef(reference, comparator)[0, 1])
        if float(np.std(reference)) > 0 and float(np.std(comparator)) > 0
        else None
    )
    regression = _deming(reference, comparator)
    subgroup_rows = []
    for subgroup in sorted({str(row["subgroup"]) for row in pairs if row["subgroup"]}):
        selected = [row for row in pairs if row["subgroup"] == subgroup]
        subgroup_rows.append(
            {
                "subgroup": subgroup,
                "pair_count": len(selected),
                "mean_paired_bias": float(np.mean([row["paired_bias"] for row in selected])),
                "categorical_agreement": float(
                    np.mean([row["call_agreement"] for row in selected])
                ),
            }
        )
    near = [
        row
        for row in pairs
        if min(
            abs(float(row["reference_score"]) - threshold),
            abs(float(row["comparator_score"]) - threshold),
        )
        <= proximity_band
    ]
    return {
        "pair_count": len(pairs),
        "paired_bias": bias,
        "paired_bias_sd": sd,
        "paired_bias_confidence_interval_95": ci,
        "bland_altman_limits_of_agreement": {
            "lower": bias - 1.96 * sd,
            "upper": bias + 1.96 * sd,
        },
        "profile_correlation": correlation,
        "correlation_passes_equivalence": False,
        "deming_regression": regression,
        "categorical_agreement": float(np.mean([row["call_agreement"] for row in pairs])),
        "discordance_rate": float(np.mean([row["discordant"] for row in pairs])),
        "discordant_pairs": [row for row in pairs if row["discordant"]],
        "tost_equivalence": {
            "margin": margin,
            "passed": ci["lower"] > -margin and ci["upper"] < margin,
            "method": "paired_mean_normal_approximation_two_one_sided_interval_rule",
        },
        "subgroup_review": subgroup_rows,
        "threshold_adjacent_review": {
            "decision_threshold": threshold,
            "proximity_band": proximity_band,
            "pair_count": len(near),
            "pairs": near,
        },
    }


def _deming(x: np.ndarray[Any, Any], y: np.ndarray[Any, Any]) -> dict[str, Any]:
    x_mean, y_mean = float(np.mean(x)), float(np.mean(y))
    sxx = float(np.var(x, ddof=1))
    syy = float(np.var(y, ddof=1))
    sxy = float(np.cov(x, y, ddof=1)[0, 1])
    if sxy == 0:
        return {"status": "NOT_ESTIMABLE", "reason": "Zero covariance."}
    slope = (syy - sxx + math.sqrt((syy - sxx) ** 2 + 4 * sxy**2)) / (2 * sxy)
    return {
        "status": "ESTIMATED",
        "slope": slope,
        "intercept": y_mean - slope * x_mean,
        "error_variance_ratio": 1.0,
    }


def _evaluate_criteria(
    criteria: list[dict[str, Any]], metrics: dict[str, Any]
) -> list[dict[str, Any]]:
    lookup = {
        "paired_bias": metrics["paired_bias"],
        "categorical_agreement": metrics["categorical_agreement"],
        "discordance_rate": metrics["discordance_rate"],
        "tost_equivalence": 1.0 if metrics["tost_equivalence"]["passed"] else 0.0,
    }
    endpoints = {
        "paired_bias": "classifier_score",
        "categorical_agreement": "predicted_class",
        "discordance_rate": "predicted_class",
        "tost_equivalence": "classifier_score",
    }
    results = []
    for criterion in criteria:
        observed = lookup.get(criterion["metric"])
        if criterion["metric"] == "profile_correlation":
            status = "NOT_APPLICABLE"
            note = "Correlation is descriptive and cannot pass equivalence."
        elif observed is None or criterion["endpoint"] != endpoints.get(criterion["metric"]):
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
                "population": "all included complete bridge pairs",
                "uncertainty": metrics["paired_bias_confidence_interval_95"]
                if criterion["metric"] == "paired_bias"
                else None,
                "note": note,
            }
        )
    return results


def _criterion_status(observed: float, operator: str, threshold: float) -> str:
    passed = {
        "gt": observed > threshold,
        "gte": observed >= threshold,
        "lt": observed < threshold,
        "lte": observed <= threshold,
        "absolute_lte": abs(observed) <= threshold,
    }.get(operator)
    return "NOT_APPLICABLE" if passed is None else "PASS" if passed else "FAIL"


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
    _write_tsv(root / "endpoints/paired_bridge_results.tsv", pairs)
    _write_tsv(
        root / "endpoints/excluded_measurements.tsv",
        [row for row in assignments if not _boolean(row.get("include", "true"))],
    )
    write_json_atomic(root / "metrics/paired_bridging_metrics.json", metrics)
    write_json_atomic(
        root / "metrics/acceptance_results.json",
        {"overall_status": overall, "criteria": criteria},
    )
    write_json_atomic(
        root / "metrics/threshold_stability.json", metrics["threshold_adjacent_review"]
    )
    summary = {
        "study_id": spec["study"]["study_id"],
        "question": spec["study"]["objective"],
        "overall_status": overall,
        "finding": f"Prespecified paired bridge criteria resolved to {overall}.",
        "criteria": criteria,
        "limitations": [
            "Correlation is descriptive and cannot pass equivalence on its own.",
            "TOST interpretation uses the scientist-prespecified margin.",
            "The locked model was applied without retraining.",
        ],
        "scientist_decision_required": True,
    }
    write_json_atomic(root / "decision/decision_summary.json", summary)
    (root / "decision/decision_summary.md").write_text(
        f"# Paired bridge decision summary\n\n**Overall:** {overall}\n\n{summary['finding']}\n"
    )
    write_json_atomic(
        root / "decision/recommendations.json",
        {"recommendations": [{"action": "SCIENTIST_REVIEW", "launch_automatically": False}]},
    )
    write_json_atomic(
        root / "decision/unresolved_questions.json", {"questions": summary["limitations"]}
    )
    _write_bland_altman(root / "figures/paired_bridge_bland_altman.svg", pairs, metrics)
    _provenance(root / "provenance", expression_bundle, model, model_manifest, spec)
    root.joinpath("report/validation_report.html").write_text(
        "<!doctype html><html><body><h1>Paired bridging study</h1>"
        f"<h2>{spec['study']['name']}</h2><p>Overall: <strong>{overall}</strong></p>"
        f"<p>Paired bias: {metrics['paired_bias']:.4f}; agreement: "
        f"{metrics['categorical_agreement']:.3f}.</p>"
        "<p>Correlation alone cannot pass equivalence. Locked model applied without "
        "retraining. Scientist decision required.</p></body></html>\n"
    )
    _pdf(
        root / "report/validation_report.pdf",
        [
            "TranscriptForge Paired Bridging Study",
            spec["study"]["name"],
            f"Overall: {overall}",
            f"Paired bias: {metrics['paired_bias']:.4f}",
            "Correlation alone cannot pass equivalence.",
            "Locked model applied without retraining.",
        ],
    )


def _write_bland_altman(
    path: Path, pairs: list[dict[str, Any]], metrics: dict[str, Any]
) -> None:
    width, height, margin = 760, 420, 70
    averages = np.asarray([row["pair_average_score"] for row in pairs], dtype=float)
    biases = np.asarray([row["paired_bias"] for row in pairs], dtype=float)
    x_min, x_max = float(np.min(averages)), float(np.max(averages))
    limits = metrics["bland_altman_limits_of_agreement"]
    y_min = min(float(np.min(biases)), float(limits["lower"]))
    y_max = max(float(np.max(biases)), float(limits["upper"]))
    x_pad, y_pad = max((x_max - x_min) * 0.1, 0.01), max((y_max - y_min) * 0.1, 0.01)
    x_min, x_max, y_min, y_max = x_min - x_pad, x_max + x_pad, y_min - y_pad, y_max + y_pad

    def sx(value: float) -> float:
        return margin + (value - x_min) / (x_max - x_min) * (width - 2 * margin)

    def sy(value: float) -> float:
        return height - margin - (value - y_min) / (y_max - y_min) * (height - 2 * margin)

    circles = "".join(
        f'<circle cx="{sx(float(row["pair_average_score"])):.1f}" '
        f'cy="{sy(float(row["paired_bias"])):.1f}" r="6" fill="#7c3aed"/>'
        for row in pairs
    )
    lines = "".join(
        f'<line x1="{margin}" y1="{sy(float(value)):.1f}" x2="{width-margin}" '
        f'y2="{sy(float(value)):.1f}" stroke="#f59e0b" stroke-dasharray="6 4"/>'
        for value in (limits["lower"], metrics["paired_bias"], limits["upper"])
    )
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/>'
        '<text x="380" y="28" text-anchor="middle" font-size="20" font-weight="700">'
        'Paired bridge Bland-Altman</text>'
        f'{lines}{circles}</svg>\n',
        encoding="utf-8",
    )
