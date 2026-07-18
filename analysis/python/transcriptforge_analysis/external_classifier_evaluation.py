"""Evaluate one locked binary-classifier prediction against separately sealed truth."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize  # type: ignore[import-untyped]
from sklearn.metrics import (  # type: ignore[import-untyped]
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    roc_auc_score,
)

from transcriptforge_analysis.matrix_validation import write_json_atomic


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evaluate_external_predictions(
    prediction_path: Path,
    truth_path: Path,
    protocol_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Join truth only after prediction artifacts exist and compute prespecified metrics."""
    prediction = json.loads(prediction_path.read_text(encoding="utf-8"))
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if "positive_class" not in prediction or "decision_threshold" not in prediction:
        raise ValueError("External evaluation v1 requires locked binary-classifier predictions.")
    if protocol.get("status") != "prospectively_frozen":
        raise ValueError("External evaluation requires a prospectively frozen protocol.")
    expected_classes = {
        str(protocol["endpoint"]["positive_class"]),
        str(protocol["endpoint"]["negative_class"]),
    }
    truth = _read_truth(truth_path, expected_classes)
    rows = prediction.get("predictions", [])
    predicted_ids = [str(row["sample_id"]) for row in rows]
    if len(predicted_ids) != len(set(predicted_ids)):
        raise ValueError("Prediction results contain duplicate sample identifiers.")
    if set(predicted_ids) != set(truth):
        raise ValueError("Prediction and sealed-truth sample identifiers do not match exactly.")
    expected_count = int(protocol["external_cohort"]["eligible_sample_count"])
    if len(rows) != expected_count:
        raise ValueError(
            f"Protocol requires {expected_count} external samples; predictions contain {len(rows)}."
        )
    if int(prediction.get("sample_count", -1)) != len(rows):
        raise ValueError("Prediction sample_count does not match its prediction rows.")
    positive_class = str(prediction["positive_class"])
    negative_class = str(prediction["negative_class"])
    if positive_class != protocol["endpoint"]["positive_class"]:
        raise ValueError("Locked model positive class disagrees with the frozen protocol.")
    if negative_class != protocol["endpoint"]["negative_class"]:
        raise ValueError("Locked model negative class disagrees with the frozen protocol.")
    y = np.asarray(
        [int(truth[sample_id] == positive_class) for sample_id in predicted_ids],
        dtype=np.int64,
    )
    probabilities = np.asarray(
        [float(row["positive_probability"]) for row in rows], dtype=np.float64
    )
    predicted = np.asarray(
        [bool(row["predicted_positive"]) for row in rows], dtype=np.bool_
    )
    if not np.all(np.isfinite(probabilities)) or np.any(
        (probabilities < 0) | (probabilities > 1)
    ):
        raise ValueError("Published probabilities must be finite values from zero through one.")
    threshold = float(prediction["decision_threshold"])
    if not np.array_equal(predicted, probabilities >= threshold):
        raise ValueError("Published classes disagree with the locked probability threshold.")
    published_classes = [str(row["predicted_class"]) for row in rows]
    expected_published_classes = [
        positive_class if is_positive else negative_class for is_positive in predicted
    ]
    if published_classes != expected_published_classes:
        raise ValueError("Published class labels disagree with the locked class direction.")

    metrics = _metrics(y, probabilities, predicted, include_calibration=True)
    evaluation = protocol["evaluation"]
    bootstrap = _bootstrap_metrics(
        y,
        probabilities,
        predicted,
        iterations=int(evaluation["bootstrap_iterations"]),
        random_seed=int(evaluation["random_seed"]),
    )
    criteria = evaluation["success_criteria"]
    point_passed = metrics["roc_auc"] >= float(criteria["minimum_point_estimate"])
    lower_passed = bootstrap["roc_auc"]["lower"] > float(
        criteria["minimum_lower_confidence_bound"]
    )
    passed = point_passed and lower_passed
    result = {
        "schema_version": "1.0.0",
        "protocol_id": protocol["protocol_id"],
        "status": "SUCCESS_CRITERIA_MET" if passed else "SUCCESS_CRITERIA_NOT_MET",
        "model_analysis_id": prediction["model_analysis_id"],
        "sample_count": len(y),
        "class_counts": {
            "negative": int(np.sum(y == 0)),
            "positive": int(np.sum(y == 1)),
        },
        "metrics": metrics,
        "confidence_intervals": {
            "method": "stratified_experimental_unit_percentile_bootstrap",
            "iterations": int(evaluation["bootstrap_iterations"]),
            "random_seed": int(evaluation["random_seed"]),
            "metrics": bootstrap,
        },
        "success": {
            "primary_metric": "roc_auc",
            "minimum_point_estimate": criteria["minimum_point_estimate"],
            "minimum_lower_confidence_bound": criteria[
                "minimum_lower_confidence_bound"
            ],
            "point_estimate_passed": bool(point_passed),
            "lower_bound_passed": bool(lower_passed),
            "passed": bool(passed),
        },
        "provenance": {
            "protocol_sha256": _sha256(protocol_path),
            "prediction_results_sha256": _sha256(prediction_path),
            "truth_sha256": _sha256(truth_path),
            "model_sha256": prediction["provenance"]["model_sha256"],
            "expression_bundle_sha256": prediction["provenance"][
                "expression_bundle_sha256"
            ],
        },
        "warnings": [
            "This is one prespecified research external validation, not clinical validation.",
            "Performance transport includes institution, biopsy, recruitment, and regimen shift.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    write_json_atomic(output_dir / "external_validation_results.json", result)
    return result


def _read_truth(path: Path, expected_classes: set[str]) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames != ["sample_id", "response"]:
            raise ValueError("Sealed truth must have exactly sample_id and response columns.")
        rows = list(reader)
    truth = {row["sample_id"].strip(): row["response"].strip() for row in rows}
    if len(truth) != len(rows) or not truth:
        raise ValueError("Sealed truth sample identifiers must be nonempty and unique.")
    if set(truth.values()) != expected_classes:
        raise ValueError("Sealed truth classes do not exactly match the frozen endpoint.")
    return truth


def _metrics(
    y: NDArray[np.int64],
    probabilities: NDArray[np.float64],
    predicted: NDArray[np.bool_],
    *,
    include_calibration: bool,
) -> dict[str, float]:
    negative_true, false_positive, false_negative, positive_true = confusion_matrix(
        y, predicted, labels=[0, 1]
    ).ravel()
    result = {
        "roc_auc": float(roc_auc_score(y, probabilities)),
        "pr_auc": float(average_precision_score(y, probabilities)),
        "prevalence": float(np.mean(y)),
        "balanced_accuracy": float(balanced_accuracy_score(y, predicted)),
        "sensitivity": float(positive_true / (positive_true + false_negative)),
        "specificity": float(negative_true / (negative_true + false_positive)),
        "brier_score": float(brier_score_loss(y, probabilities)),
    }
    if include_calibration:
        intercept, slope = _calibration(y, probabilities)
        result["calibration_intercept"] = intercept
        result["calibration_slope"] = slope
    return result


def _calibration(
    y: NDArray[np.int64], probabilities: NDArray[np.float64]
) -> tuple[float, float]:
    logits = np.log(
        np.clip(probabilities, 1e-8, 1 - 1e-8)
        / np.clip(1 - probabilities, 1e-8, 1)
    )

    def objective(parameters: NDArray[np.float64]) -> float:
        linear = np.clip(parameters[0] + parameters[1] * logits, -36, 36)
        return float(np.sum(np.logaddexp(0, linear) - y * linear))

    fitted = minimize(objective, np.asarray([0.0, 1.0]), method="BFGS")
    if not np.all(np.isfinite(fitted.x)):
        raise ValueError("External calibration diagnostics could not be estimated.")
    return float(fitted.x[0]), float(fitted.x[1])


def _bootstrap_metrics(
    y: NDArray[np.int64],
    probabilities: NDArray[np.float64],
    predicted: NDArray[np.bool_],
    *,
    iterations: int,
    random_seed: int,
) -> dict[str, dict[str, float]]:
    rng = np.random.default_rng(random_seed)
    negative = np.flatnonzero(y == 0)
    positive = np.flatnonzero(y == 1)
    names = (
        "roc_auc",
        "pr_auc",
        "balanced_accuracy",
        "sensitivity",
        "specificity",
        "brier_score",
    )
    values: dict[str, list[float]] = {name: [] for name in names}
    for _ in range(iterations):
        indices = np.concatenate(
            (
                rng.choice(negative, size=len(negative), replace=True),
                rng.choice(positive, size=len(positive), replace=True),
            )
        )
        sampled = _metrics(
            y[indices], probabilities[indices], predicted[indices], include_calibration=False
        )
        for name in names:
            values[name].append(sampled[name])
    return {
        name: {
            "lower": float(np.quantile(observed, 0.025)),
            "upper": float(np.quantile(observed, 0.975)),
        }
        for name, observed in values.items()
    }
