"""Locked-model input/degradation limit Analytical Study."""

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


def run_input_degradation_limit_study(
    bundle: Path,
    model: Path,
    model_manifest: Path,
    study_spec: Path,
    assignments_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Apply one locked model once and evaluate ordered-level stability criteria."""
    spec = json.loads(study_spec.read_text(encoding="utf-8"))
    _validate_spec(spec, model_manifest)
    assignments = _read_tsv(assignments_path)
    _validate_assignments(assignments, spec)
    output_dir.mkdir(parents=True, exist_ok=False)
    prediction_dir = output_dir / "_locked_prediction"
    prediction = predict_with_model(bundle, model, prediction_dir, model_manifest)
    prediction_by_sample = {row["sample_id"]: row for row in prediction["predictions"]}
    included = [row for row in assignments if _boolean(row.get("include", "true"))]
    assignment_ids = {row["measurement_id"] for row in included}
    if assignment_ids != set(prediction_by_sample):
        raise ValueError("Study assignments must map every prediction sample exactly once.")
    reference_level = float(spec["analysis_plan"]["reference_level"])
    raw_endpoints: list[dict[str, Any]] = []
    for row in included:
        predicted = prediction_by_sample[row["measurement_id"]]
        score = (
            float(predicted["positive_probability"])
            if "positive_probability" in predicted
            else float(max(predicted["class_probabilities"].values()))
        )
        raw_endpoints.append(
            {
                **row,
                "input_level": float(row["input_level"]),
                "quality_metric": _optional_float(row.get("quality_metric", "")),
                "qc_failure": _boolean(row.get("qc_failure", "false")),
                "classifier_score": score,
                "predicted_class": predicted["predicted_class"],
            }
        )
    by_sample: dict[str, dict[float, dict[str, Any]]] = defaultdict(dict)
    for row in raw_endpoints:
        by_sample[row["biological_sample_id"]][float(row["input_level"])] = row
    endpoints: list[dict[str, Any]] = []
    for row in raw_endpoints:
        reference = by_sample[row["biological_sample_id"]][reference_level]
        endpoints.append(
            {
                **row,
                "reference_measurement_id": reference["measurement_id"],
                "score_difference_from_reference": float(row["classifier_score"])
                - float(reference["classifier_score"]),
                "absolute_score_difference_from_reference": abs(
                    float(row["classifier_score"]) - float(reference["classifier_score"])
                ),
                "call_agreement_to_reference": row["predicted_class"]
                == reference["predicted_class"],
                "threshold_crossing_from_reference": row["predicted_class"]
                != reference["predicted_class"],
            }
        )
    metrics = _ordered_metrics(endpoints, reference_level, prediction)
    criteria = _evaluate_criteria(spec["acceptance_criteria"], metrics, reference_level)
    candidate_level = _candidate_level(metrics["levels"], criteria, reference_level)
    overall = (
        "FAIL"
        if any(item["status"] == "FAIL" for item in criteria)
        else "INDETERMINATE"
        if any(item["status"] in {"INDETERMINATE", "NOT_APPLICABLE"} for item in criteria)
        else "PASS"
    )
    metrics["candidate_lowest_tested_level"] = candidate_level
    metrics["candidate_interpretation"] = (
        "Lowest tested consecutive level meeting every computable declared criterion; "
        "this is not automatically a clinical LoD."
    )
    bundle_dir = output_dir / "validation_bundle"
    _write_bundle(
        bundle_dir,
        spec,
        assignments,
        endpoints,
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


def _validate_spec(spec: dict[str, Any], model_manifest_path: Path) -> None:
    schema = json.loads((CONTRACT_ROOT / "study_spec.schema.json").read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(spec), key=lambda error: list(error.path)
    )
    if errors:
        location = ".".join(str(value) for value in errors[0].path) or "document"
        raise ValueError(f"StudySpec violates its contract at {location}: {errors[0].message}")
    if spec["study"]["type"] != "INPUT_DEGRADATION_LIMIT":
        raise ValueError("The input/degradation runner requires INPUT_DEGRADATION_LIMIT.")
    if spec["model"]["manifest_sha256"] != _sha(model_manifest_path):
        raise ValueError("StudySpec model manifest checksum does not match the locked input.")
    manifest = json.loads(model_manifest_path.read_text(encoding="utf-8"))
    if manifest.get("model_id") != spec["model"]["model_id"]:
        raise ValueError("StudySpec model identity does not match the locked ModelManifest.")


def _validate_assignments(rows: list[dict[str, str]], spec: dict[str, Any]) -> None:
    required = {"measurement_id", "biological_sample_id", "input_level", "run", "include"}
    if not rows or required - set(rows[0]):
        raise ValueError("Input/degradation assignments lack required columns.")
    included = [row for row in rows if _boolean(row["include"])]
    identifiers = [row["measurement_id"] for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Study measurement identifiers must be unique.")
    levels = sorted({float(row["input_level"]) for row in included}, reverse=True)
    reference = float(spec["analysis_plan"]["reference_level"])
    if reference not in levels or len(levels) < 3:
        raise ValueError("The reference and at least three ordered levels must be present.")
    by_sample: dict[str, list[float]] = defaultdict(list)
    for row in included:
        by_sample[row["biological_sample_id"]].append(float(row["input_level"]))
    if len(by_sample) < 3 or any(sorted(values) != sorted(levels) for values in by_sample.values()):
        raise ValueError("Every biological sample requires exactly one measurement at each level.")


def _optional_float(value: str) -> float | None:
    if not value.strip():
        return None
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("quality_metric must be finite.")
    return parsed


def _ordered_metrics(
    rows: list[dict[str, Any]], reference_level: float, prediction: dict[str, Any]
) -> dict[str, Any]:
    level_results: list[dict[str, Any]] = []
    for level in sorted({float(row["input_level"]) for row in rows}, reverse=True):
        selected = [row for row in rows if float(row["input_level"]) == level]
        differences = np.asarray(
            [float(row["score_difference_from_reference"]) for row in selected], dtype=float
        )
        mean = float(np.mean(differences))
        se = float(np.std(differences, ddof=1) / math.sqrt(len(differences)))
        level_results.append(
            {
                "input_level": level,
                "measurement_count": len(selected),
                "mean_score": float(np.mean([row["classifier_score"] for row in selected])),
                "mean_score_difference": mean,
                "mean_absolute_score_difference": float(
                    np.mean([row["absolute_score_difference_from_reference"] for row in selected])
                ),
                "score_difference_confidence_interval_95": {
                    "lower": mean - 1.96 * se,
                    "upper": mean + 1.96 * se,
                    "method": "normal_approximation_paired",
                },
                "call_agreement_to_reference": float(
                    np.mean([row["call_agreement_to_reference"] for row in selected])
                ),
                "threshold_crossing_count": sum(
                    bool(row["threshold_crossing_from_reference"]) for row in selected
                ),
                "qc_failure_rate": float(np.mean([row["qc_failure"] for row in selected])),
                "paired_reference": level == reference_level,
            }
        )
    level_values = np.asarray([item["input_level"] for item in level_results], dtype=float)
    score_values = np.asarray([item["mean_score"] for item in level_results], dtype=float)
    slope = float(np.polyfit(level_values, score_values, 1)[0])
    adjacent: list[dict[str, Any]] = [
        {
            "upper_level": level_results[index]["input_level"],
            "lower_level": level_results[index + 1]["input_level"],
            "absolute_mean_score_change": abs(
                float(level_results[index + 1]["mean_score"])
                - float(level_results[index]["mean_score"])
            ),
        }
        for index in range(len(level_results) - 1)
    ]
    change_point = max(adjacent, key=lambda item: item["absolute_mean_score_change"])
    threshold = float(prediction.get("decision_threshold", 0.5))
    return {
        "levels": level_results,
        "trend": {
            "score_per_input_unit_slope": slope,
            "method": "descriptive_ordinary_least_squares_on_level_means",
        },
        "change_point_exploration": {
            **change_point,
            "method": "largest_adjacent_absolute_mean_score_change",
            "exploratory": True,
        },
        "threshold_stability": {
            "decision_threshold": threshold,
            "near_threshold_count": sum(
                abs(float(row["classifier_score"]) - threshold)
                <= float(prediction.get("threshold_proximity_band", 0.1))
                for row in rows
            ),
            "threshold_crossing_count": sum(
                bool(row["threshold_crossing_from_reference"]) for row in rows
            ),
        },
    }


def _evaluate_criteria(
    criteria: list[dict[str, Any]], metrics: dict[str, Any], reference_level: float
) -> list[dict[str, Any]]:
    expected = {
        "mean_absolute_score_difference": ("classifier_score", "lte"),
        "call_agreement_to_reference": ("predicted_class", "gte"),
        "qc_failure_rate": ("qc_failure", "lte"),
    }
    results = []
    nonreference = [
        item for item in metrics["levels"] if float(item["input_level"]) != reference_level
    ]
    for criterion in criteria:
        definition = expected.get(criterion["metric"])
        if definition is None or criterion["endpoint"] != definition[0]:
            status, passing = "NOT_APPLICABLE", []
        else:
            passing = [
                float(item["input_level"])
                for item in nonreference
                if _passes(
                    float(item[criterion["metric"]]),
                    definition[1],
                    float(criterion["threshold"]),
                )
            ]
            if criterion["operator"] == "all_levels":
                status = "PASS" if len(passing) == len(nonreference) else "FAIL"
            elif criterion["operator"] == "consecutive_levels":
                status = "PASS" if _consecutive_levels(nonreference, passing) else "FAIL"
            elif criterion["operator"] in {"lte", "gte", "lt", "gt", "absolute_lte"}:
                status = "PASS" if len(passing) == len(nonreference) else "FAIL"
            else:
                status = "NOT_APPLICABLE"
        results.append(
            {
                **criterion,
                "observed": {
                    str(item["input_level"]): item.get(criterion["metric"])
                    for item in nonreference
                },
                "passing_levels": passing,
                "status": status,
                "population": "all included paired measurements by ordered level",
                "uncertainty": "paired level-specific confidence intervals are reported separately",
            }
        )
    return results


def _passes(observed: float, operator: str, threshold: float) -> bool:
    return {
        "lte": observed <= threshold,
        "gte": observed >= threshold,
        "lt": observed < threshold,
        "gt": observed > threshold,
    }.get(operator, abs(observed) <= threshold)


def _consecutive_levels(levels: list[dict[str, Any]], passing: list[float]) -> bool:
    consecutive = 0
    for item in levels:
        if float(item["input_level"]) in passing:
            consecutive += 1
        else:
            break
    return consecutive >= 2


def _candidate_level(
    levels: list[dict[str, Any]], criteria: list[dict[str, Any]], reference_level: float
) -> float | None:
    applicable = [item for item in criteria if item["status"] != "NOT_APPLICABLE"]
    if not applicable:
        return None
    common = set.intersection(*(set(item["passing_levels"]) for item in applicable))
    consecutive: list[float] = []
    for item in levels:
        level = float(item["input_level"])
        if level == reference_level:
            continue
        if level not in common:
            break
        consecutive.append(level)
    return min(consecutive) if consecutive else None


def _write_bundle(
    root: Path,
    spec: dict[str, Any],
    assignments: list[dict[str, str]],
    endpoints: list[dict[str, Any]],
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
    _write_tsv(
        root / "endpoints/excluded_measurements.tsv",
        [row for row in assignments if not _boolean(row.get("include", "true"))],
    )
    write_json_atomic(root / "metrics/input_degradation_metrics.json", metrics)
    write_json_atomic(
        root / "metrics/acceptance_results.json",
        {"overall_status": overall, "criteria": criteria},
    )
    write_json_atomic(root / "metrics/threshold_stability.json", metrics["threshold_stability"])
    summary = {
        "study_id": spec["study"]["study_id"],
        "question": spec["study"]["objective"],
        "overall_status": overall,
        "finding": (
            f"Prespecified ordered-level criteria resolved to {overall}; candidate lowest "
            f"tested level: {metrics['candidate_lowest_tested_level']}."
        ),
        "criteria": criteria,
        "limitations": [
            "The lowest passing tested level is not automatically a clinical LoD.",
            "Change-point analysis is exploratory and does not override prespecified criteria.",
            "The locked model was applied without retraining.",
        ],
        "scientist_decision_required": True,
    }
    write_json_atomic(root / "decision/decision_summary.json", summary)
    (root / "decision/decision_summary.md").write_text(
        f"# Validation decision summary\n\n**Overall:** {overall}\n\n{summary['finding']}\n"
    )
    write_json_atomic(
        root / "decision/recommendations.json",
        {"recommendations": [{"action": "SCIENTIST_REVIEW", "launch_automatically": False}]},
    )
    write_json_atomic(
        root / "decision/unresolved_questions.json", {"questions": summary["limitations"]}
    )
    _write_level_figure(root / "figures/score_stability_by_level.svg", metrics["levels"])
    _provenance(root / "provenance", expression_bundle, model, model_manifest, spec)
    root.joinpath("report/validation_report.html").write_text(
        "<!doctype html><html><body><h1>Input/degradation limit study</h1>"
        f"<h2>{spec['study']['name']}</h2><p>Overall: <strong>{overall}</strong></p>"
        f"<p>Candidate lowest tested level: {metrics['candidate_lowest_tested_level']}</p>"
        "<p>This does not automatically establish a clinical LoD. Locked model applied "
        "without retraining. Scientist decision required.</p></body></html>\n"
    )
    _pdf(
        root / "report/validation_report.pdf",
        [
            "TranscriptForge Input/Degradation Limit Study",
            spec["study"]["name"],
            f"Overall: {overall}",
            f"Candidate lowest tested level: {metrics['candidate_lowest_tested_level']}",
            "This does not automatically establish a clinical LoD.",
            "Locked model applied without retraining.",
        ],
    )


def _write_level_figure(path: Path, levels: list[dict[str, Any]]) -> None:
    width, height, margin = 760, 420, 70
    minimum = min(float(item["mean_score"]) for item in levels)
    maximum = max(float(item["mean_score"]) for item in levels)
    padding = max((maximum - minimum) * 0.1, 0.01)
    minimum, maximum = minimum - padding, maximum + padding
    points = []
    for index, item in enumerate(levels):
        x = margin + index * (width - 2 * margin) / max(len(levels) - 1, 1)
        y = height - margin - (float(item["mean_score"]) - minimum) / (maximum - minimum) * (
            height - 2 * margin
        )
        points.append((x, y, item))
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points)
    circles = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#7c3aed">'
        f'<title>{item["input_level"]}: {item["mean_score"]:.3f}</title></circle>'
        for x, y, item in points
    )
    labels = "".join(
        f'<text x="{x:.1f}" y="{height-35}" text-anchor="middle" font-size="13">'
        f'{item["input_level"]:g}</text>'
        for x, _, item in points
    )
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/>'
        '<text x="380" y="28" text-anchor="middle" font-size="20" font-weight="700">'
        'Locked score stability by ordered level</text>'
        f'<line x1="{margin}" y1="{height-margin}" x2="{width-margin}" '
        f'y2="{height-margin}" stroke="#334155"/><line x1="{margin}" y1="{margin}" '
        f'x2="{margin}" y2="{height-margin}" stroke="#334155"/>'
        f'<polyline points="{polyline}" fill="none" stroke="#7c3aed" '
        f'stroke-width="3"/>{circles}{labels}</svg>\n',
        encoding="utf-8",
    )
