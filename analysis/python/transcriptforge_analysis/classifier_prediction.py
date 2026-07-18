"""Apply a locked TranscriptForge classifier to a compatible Expression Bundle."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from transcriptforge_analysis.matrix_validation import write_json_atomic
from transcriptforge_analysis.pca import load_bundle_assay


def predict_with_model(bundle_archive: Path, model_path: Path, output_dir: Path) -> dict[str, Any]:
    """Validate feature compatibility and apply a previously locked linear model."""
    model = json.loads(model_path.read_text(encoding="utf-8"))
    _validate_model(model)
    bundle = load_bundle_assay(bundle_archive, str(model["assay"]))
    output_dir.mkdir(parents=True, exist_ok=False)

    selected = cast(list[str], model["selected_feature_ids"])
    feature_lookup = {feature_id: index for index, feature_id in enumerate(bundle.feature_ids)}
    missing = [feature_id for feature_id in selected if feature_id not in feature_lookup]
    if missing:
        preview = ", ".join(missing[:5])
        raise ValueError(
            f"Inference blocked: {len(missing)} required model feature(s) are missing: {preview}."
        )
    indices = np.asarray([feature_lookup[feature_id] for feature_id in selected], dtype=np.int64)
    matrix = np.asarray(bundle.matrix[indices, :].T, dtype=np.float64)
    if not np.all(np.isfinite(matrix)):
        raise ValueError("Inference blocked: required expression values contain non-finite values.")

    preprocessing = cast(dict[str, Any], model["preprocessing"])
    estimator = cast(dict[str, Any], model["estimator"])
    means = np.asarray(preprocessing["means"], dtype=np.float64)
    scales = np.asarray(preprocessing["scales"], dtype=np.float64)
    coefficients = np.asarray(estimator["coefficients"], dtype=np.float64)
    transformed = (matrix - means) / scales
    overlap = {
        "required_feature_count": len(selected),
        "matched_feature_count": len(selected),
        "missing_feature_count": 0,
        "bundle_feature_count": len(bundle.feature_ids),
        "overlap_fraction": 1.0,
    }
    common = {
        "schema_version": "1.0.0",
        "model_analysis_id": model["analysis_id"],
        "model_prepared_dataset_id": model["prepared_dataset_id"],
        "assay": model["assay"],
        "sample_count": len(bundle.sample_ids),
        "feature_overlap": overlap,
        "provenance": {
            "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
            "expression_bundle_sha256": hashlib.sha256(bundle_archive.read_bytes()).hexdigest(),
        },
        "warnings": [
            "Predictions are research-only and do not establish external or clinical validity."
        ],
    }
    if model["model_type"] == "binary_elastic_net_logistic_regression":
        decisions = transformed @ coefficients + float(estimator["intercept"])
        probabilities = _calibrate(decisions, cast(dict[str, Any], model["calibration"]))
        threshold = float(model["decision_threshold"])
        positive = probabilities >= threshold
        predictions = [
            {
                "sample_id": sample_id,
                "positive_probability": float(probabilities[index]),
                "predicted_positive": bool(positive[index]),
                "predicted_class": model["positive_class"]
                if positive[index]
                else model["negative_class"],
            }
            for index, sample_id in enumerate(bundle.sample_ids)
        ]
        result = {
            **common,
            "negative_class": model["negative_class"],
            "positive_class": model["positive_class"],
            "decision_threshold": threshold,
            "predictions": predictions,
        }
    else:
        classes = cast(list[str], model["classes"])
        logits = transformed @ coefficients.T + np.asarray(estimator["intercepts"])
        probabilities = _softmax(logits)
        predicted = np.argmax(probabilities, axis=1)
        predictions = [
            {
                "sample_id": sample_id,
                "predicted_class": classes[int(predicted[index])],
                "class_probabilities": {
                    label: float(probabilities[index, class_index])
                    for class_index, label in enumerate(classes)
                },
            }
            for index, sample_id in enumerate(bundle.sample_ids)
        ]
        result = {
            **common,
            "classes": classes,
            "prediction_rule": "maximum_class_probability",
            "predictions": predictions,
        }
    write_json_atomic(output_dir / "prediction_results.json", result)
    write_json_atomic(output_dir / "feature_overlap.json", overlap)
    _write_predictions(output_dir / "predictions.tsv", predictions)
    write_json_atomic(output_dir / "result_manifest.json", _result_manifest(result))
    return result


def _validate_model(model: dict[str, Any]) -> None:
    common = {
        "schema_version",
        "model_type",
        "analysis_id",
        "prepared_dataset_id",
        "assay",
        "selected_feature_ids",
        "preprocessing",
        "estimator",
    }
    model_type = model.get("model_type")
    if model_type == "binary_elastic_net_logistic_regression":
        required = common | {
            "negative_class",
            "positive_class",
            "calibration",
            "decision_threshold",
        }
    elif model_type == "multiclass_elastic_net_logistic_regression":
        required = common | {"classes", "prediction_rule"}
    else:
        raise ValueError("Unsupported locked model schema or model type.")
    missing_keys = sorted(required - set(model))
    if missing_keys:
        raise ValueError(f"Locked model is missing required field(s): {', '.join(missing_keys)}.")
    if model["schema_version"] != "1.0.0":
        raise ValueError("Unsupported locked model schema or model type.")
    features = model["selected_feature_ids"]
    if not isinstance(features, list) or not features or len(features) != len(set(features)):
        raise ValueError("Locked model feature identifiers must be nonempty and unique.")
    lengths = {
        len(features),
        len(model["preprocessing"].get("means", [])),
        len(model["preprocessing"].get("scales", [])),
    }
    coefficients = model["estimator"].get("coefficients", [])
    if model_type == "binary_elastic_net_logistic_regression":
        lengths.add(len(coefficients))
    else:
        classes = model["classes"]
        if (
            not isinstance(classes, list)
            or len(classes) < 3
            or len(classes) != len(set(classes))
            or len(coefficients) != len(classes)
            or len(model["estimator"].get("intercepts", [])) != len(classes)
            or any(len(row) != len(features) for row in coefficients)
        ):
            raise ValueError("Locked multiclass model class and coefficient dimensions disagree.")
    if len(lengths) != 1:
        raise ValueError("Locked model feature and coefficient dimensions do not agree.")
    scales = np.asarray(model["preprocessing"]["scales"], dtype=np.float64)
    if np.any(~np.isfinite(scales)) or np.any(scales <= 0):
        raise ValueError("Locked model preprocessing scales must be finite and positive.")


def _calibrate(decisions: NDArray[np.float64], calibration: dict[str, Any]) -> NDArray[np.float64]:
    if calibration["method"] == "sigmoid":
        decisions = decisions * float(calibration["coefficient"]) + float(calibration["intercept"])
    elif calibration["method"] != "none":
        raise ValueError("Locked model uses an unsupported calibration method.")
    clipped = np.clip(decisions, -709, 709)
    return 1.0 / (1.0 + np.exp(-clipped))


def _softmax(logits: NDArray[np.float64]) -> NDArray[np.float64]:
    shifted = logits - np.max(logits, axis=1, keepdims=True)
    exponential = np.exp(shifted)
    return cast(NDArray[np.float64], exponential / np.sum(exponential, axis=1, keepdims=True))


def _write_predictions(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _result_manifest(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "analysis_type": "classifier",
        "title": "Locked classifier predictions",
        "summary_metrics": [
            {"label": "Samples predicted", "value": result["sample_count"]},
            {
                "label": "Required features matched",
                "value": result["feature_overlap"]["matched_feature_count"],
            },
        ],
        "sections": [
            {
                "id": "predictions",
                "title": "Research predictions",
                "items": [
                    {"type": "table", "title": "Predictions", "path": "predictions.tsv"},
                    {
                        "type": "file",
                        "title": "Feature compatibility audit",
                        "path": "feature_overlap.json",
                    },
                ],
            }
        ],
        "downloads": [
            {
                "type": "file",
                "title": "Structured prediction results",
                "path": "prediction_results.json",
            },
            {"type": "table", "title": "Predictions", "path": "predictions.tsv"},
        ],
        "warnings": result["warnings"],
    }
