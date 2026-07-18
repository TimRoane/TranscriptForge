"""Tests for the frozen external-classifier evaluation boundary."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from transcriptforge_analysis.external_classifier_evaluation import (
    evaluate_external_predictions,
)

ROOT = Path(__file__).parents[3]


def _write_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    samples = [f"sample_{index:02d}" for index in range(20)]
    probabilities = [
        0.04,
        0.08,
        0.12,
        0.16,
        0.20,
        0.24,
        0.28,
        0.32,
        0.36,
        0.40,
        0.60,
        0.64,
        0.68,
        0.72,
        0.76,
        0.80,
        0.84,
        0.88,
        0.92,
        0.96,
    ]
    prediction: dict[str, Any] = {
        "schema_version": "1.0.0",
        "model_analysis_id": "locked-model-1",
        "model_prepared_dataset_id": "development-bundle-1",
        "assay": "log_expression",
        "negative_class": "nCR",
        "positive_class": "pCR",
        "decision_threshold": 0.5,
        "sample_count": len(samples),
        "feature_overlap": {
            "required_feature_count": 10,
            "matched_feature_count": 10,
            "missing_feature_count": 0,
            "bundle_feature_count": 100,
            "overlap_fraction": 1.0,
        },
        "predictions": [
            {
                "sample_id": sample,
                "positive_probability": probability,
                "predicted_positive": probability >= 0.5,
                "predicted_class": "pCR" if probability >= 0.5 else "nCR",
            }
            for sample, probability in zip(samples, probabilities, strict=True)
        ],
        "provenance": {
            "model_sha256": "a" * 64,
            "expression_bundle_sha256": "b" * 64,
        },
        "warnings": ["Research use only."],
    }
    prediction_path = tmp_path / "predictions.json"
    prediction_path.write_text(json.dumps(prediction), encoding="utf-8")

    truth_path = tmp_path / "truth.tsv"
    with truth_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["sample_id", "response"])
        writer.writerows(
            (sample, "nCR" if index < 10 else "pCR")
            for index, sample in enumerate(samples)
        )

    protocol = json.loads(
        (ROOT / "demo/classifier_external_validation/gse32646_protocol.json").read_text(
            encoding="utf-8"
        )
    )
    protocol["external_cohort"]["eligible_sample_count"] = len(samples)
    protocol["external_cohort"]["class_counts"] = {"pCR": 10, "nCR": 10}
    protocol["evaluation"]["bootstrap_iterations"] = 1000
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
    return prediction_path, truth_path, protocol_path


def test_external_evaluation_is_schema_valid_and_deterministic(tmp_path: Path) -> None:
    prediction_path, truth_path, protocol_path = _write_fixture(tmp_path)
    first = evaluate_external_predictions(
        prediction_path, truth_path, protocol_path, tmp_path / "evaluation-1"
    )
    second = evaluate_external_predictions(
        prediction_path, truth_path, protocol_path, tmp_path / "evaluation-2"
    )

    schema = json.loads(
        (ROOT / "schemas/classifier_external_validation_results.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema).validate(first)
    assert first == second
    assert first["status"] == "SUCCESS_CRITERIA_MET"
    assert first["metrics"]["roc_auc"] == 1.0
    assert first["success"]["passed"] is True


def test_external_evaluation_rejects_truth_sample_mismatch(tmp_path: Path) -> None:
    prediction_path, truth_path, protocol_path = _write_fixture(tmp_path)
    truth = truth_path.read_text(encoding="utf-8").replace("sample_00", "unknown")
    truth_path.write_text(truth, encoding="utf-8")

    with pytest.raises(ValueError, match="sample identifiers do not match exactly"):
        evaluate_external_predictions(
            prediction_path, truth_path, protocol_path, tmp_path / "evaluation"
        )
