#!/usr/bin/env python3
"""Freeze the prespecified GSE140494 classifier request and split audit."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from transcriptforge_api.services.classifier_design import _build_fold_plan

ROOT = Path(__file__).resolve().parents[2]
RANDOM_SEED = 20260717


def freeze_request(metadata: Path, output: Path) -> dict[str, object]:
    with metadata.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    outcomes = [row["response"] for row in rows]
    groups = [row["patient_id"] for row in rows]
    fold_plan, errors = _build_fold_plan(
        outcomes,
        groups,
        outer_folds=5,
        inner_folds=4,
        repeats=5,
        random_seed=RANDOM_SEED,
        expected_class_count=2,
    )
    if errors:
        raise ValueError("Frozen development split is infeasible: " + "; ".join(errors))
    request: dict[str, object] = {
        "schema_version": "1.0.0",
        "analysis_id": "breast-pcr-gse140494-v1",
        "prepared_dataset_id": "gse140494-development",
        "analysis_type": "classifier",
        "method": "elastic_net",
        "assay": "log_expression",
        "parameters": {
            "outcome_column": "response",
            "positive_class": "pCR",
            "group_column": "patient_id",
            "cohort_column": None,
            "validation_mode": "repeated_nested_cross_validation",
            "feature_filter": "top_variance",
            "top_variable_features": 500,
            "class_weight": "balanced",
            "outer_folds": 5,
            "inner_folds": 4,
            "repeats": 5,
            "primary_metric": "roc_auc",
            "probability_calibration": "sigmoid",
            "decision_threshold_strategy": "inner_cv_youden",
            "bootstrap_iterations": 2000,
            "permutation_count": 100,
        },
        "random_seed": RANDOM_SEED,
        "design_validation": {
            "valid": True,
            "eligible_sample_count": len(rows),
            "class_counts": {
                "pCR": outcomes.count("pCR"),
                "nCR": outcomes.count("nCR"),
            },
            "group_column": "patient_id",
            "group_count": len(set(groups)),
            "expected_oof_prediction_count": len(rows) * 5,
            "fold_plan": [item.model_dump(mode="json") for item in fold_plan],
        },
        "leakage_policy": {
            "preprocessing_scope": "fit_inside_each_training_fold",
            "feature_selection_scope": "fit_inside_each_training_fold",
            "hyperparameter_tuning_scope": "inner_training_folds_only",
            "outer_test_fold_role": "evaluation_only",
        },
    }
    schema = json.loads((ROOT / "schemas/analysis_request.schema.json").read_text())
    Draft202012Validator(schema).validate(request)
    output.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    return request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    freeze_request(args.metadata.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
