"""Grouped nested-CV classifier and leakage-trap acceptance tests."""

import hashlib
import io
import json
import tarfile
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from sklearn.model_selection import StratifiedGroupKFold  # type: ignore[import-untyped]
from transcriptforge_analysis.classifier import (
    ClassifierConfig,
    _permuted_labels,
    run_classifier,
    validate_leakage_audit,
)
from transcriptforge_analysis.classifier_prediction import predict_with_model

ROOT = Path(__file__).parents[3]


def _bundle(path: Path) -> tuple[list[str], list[str], list[str]]:
    rng = np.random.default_rng(20260717)
    sample_ids: list[str] = []
    outcomes: list[str] = []
    groups: list[str] = []
    cohorts: list[str] = []
    for subject in range(12):
        for condition in ("control", "treated"):
            sample_ids.append(f"subject_{subject + 1:02d}_{condition}")
            outcomes.append(condition)
            groups.append(f"subject_{subject + 1:02d}")
            cohorts.append("site_A" if subject < 6 else "site_B")
    matrix = rng.normal(0, 0.35, size=(40, len(sample_ids)))
    treated = np.asarray([item == "treated" for item in outcomes])
    matrix[:6, treated] += 2.5
    matrix[6:10, treated] -= 2.0
    assay_lines = ["feature_id\t" + "\t".join(sample_ids)]
    assay_lines.extend(
        f"gene_{feature + 1:03d}\t" + "\t".join(f"{value:.8f}" for value in matrix[feature])
        for feature in range(matrix.shape[0])
    )
    metadata_lines = ["sample_id\tcondition\tsubject_id\tcohort"]
    metadata_lines.extend(
        "\t".join(row) for row in zip(sample_ids, outcomes, groups, cohorts, strict=True)
    )
    files = {
        "expression_bundle/bundle_manifest.json": json.dumps(
            {
                "assays": [{"name": "log_expression", "path": "assays/log_expression.tsv"}],
                "sample_metadata": "metadata/sample_metadata.tsv",
            }
        ).encode(),
        "expression_bundle/assays/log_expression.tsv": ("\n".join(assay_lines) + "\n").encode(),
        "expression_bundle/metadata/sample_metadata.tsv": (
            "\n".join(metadata_lines) + "\n"
        ).encode(),
    }
    with tarfile.open(path, "w:gz") as archive:
        for name, payload in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            member.mtime = 0
            archive.addfile(member, io.BytesIO(payload))
    return sample_ids, outcomes, groups


def _fold_plan(outcomes: list[str], groups: list[str]) -> tuple[dict[str, object], ...]:
    y = np.asarray(outcomes)
    group_array = np.asarray(groups)
    plan: list[dict[str, object]] = []
    for repeat in range(2):
        splitter = StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=20260717 + repeat)
        for fold, (training, test) in enumerate(
            splitter.split(np.zeros((len(y), 1)), y, group_array), 1
        ):
            train_counts = Counter(y[training].tolist())
            test_counts = Counter(y[test].tolist())
            plan.append(
                {
                    "repeat": repeat + 1,
                    "fold": fold,
                    "training_sample_count": len(training),
                    "test_sample_count": len(test),
                    "training_class_counts": dict(train_counts),
                    "test_class_counts": dict(test_counts),
                    "training_group_count": len(set(group_array[training].tolist())),
                    "test_group_count": len(set(group_array[test].tolist())),
                    "group_overlap_count": 0,
                }
            )
    return tuple(plan)


def test_grouped_nested_classifier_emits_complete_deterministic_oof_results(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "bundle.tar.gz"
    sample_ids, outcomes, groups = _bundle(archive)
    request = tmp_path / "analysis-request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "analysis_id": "classifier-1",
                "prepared_dataset_id": "prepared-1",
                "analysis_type": "classifier",
                "method": "elastic_net",
                "assay": "log_expression",
                "parameters": {
                    "outcome_column": "condition",
                    "positive_class": "treated",
                    "group_column": "subject_id",
                    "cohort_column": "cohort",
                    "validation_mode": "repeated_nested_cross_validation",
                    "feature_filter": "top_variance",
                    "top_variable_features": 10,
                    "class_weight": "balanced",
                    "outer_folds": 3,
                    "inner_folds": 2,
                    "repeats": 2,
                    "primary_metric": "roc_auc",
                    "probability_calibration": "sigmoid",
                    "decision_threshold_strategy": "inner_cv_youden",
                    "bootstrap_iterations": 200,
                    "permutation_count": 5,
                },
                "random_seed": 20260717,
                "design_validation": {
                    "valid": True,
                    "fold_plan": _fold_plan(outcomes, groups),
                },
                "leakage_policy": {
                    "preprocessing_scope": "fit_inside_each_training_fold",
                    "feature_selection_scope": "fit_inside_each_training_fold",
                    "hyperparameter_tuning_scope": "inner_training_folds_only",
                    "outer_test_fold_role": "evaluation_only",
                },
            }
        ),
        encoding="utf-8",
    )
    request_schema = json.loads((ROOT / "schemas/analysis_request.schema.json").read_text())
    Draft202012Validator(request_schema).validate(json.loads(request.read_text()))
    config = ClassifierConfig.from_json(request)
    first = tmp_path / "first"
    second = tmp_path / "second"
    result = run_classifier(archive, config, first, permutation_workers=1)
    run_classifier(archive, config, second, permutation_workers=2)

    assert result["oof_coverage"] == {
        "expected_prediction_count": 48,
        "observed_prediction_count": 48,
        "one_prediction_per_sample_per_repeat": True,
    }
    counts = Counter((item["sample_id"], item["repeat"]) for item in result["oof_predictions"])
    assert set(counts) == {(sample_id, repeat) for sample_id in sample_ids for repeat in (1, 2)}
    assert set(counts.values()) == {1}
    assert all(item["group_overlap_count"] == 0 for item in result["folds"])
    assert result["metrics"]["roc_auc"] > 0.95
    assert result["metrics"]["pr_auc"] > 0.95
    assert len(result["repeat_metrics"]) == 2
    assert result["confidence_intervals"]["iterations"] == 200
    assert result["permutation_control"]["count"] == 5
    assert len(result["learning_curve"]) == 3
    assert [item["method"] for item in result["model_comparisons"]] == [
        "elastic_net",
        "random_forest",
        "hist_gradient_boosting",
    ]
    assert all(
        item["tuning_scope"] == "inner_training_folds_only" for item in result["model_comparisons"]
    )
    assert result["leakage_audit"]["all_fold_scopes_disjoint"] is True
    assert (first / "classifier_results.json").read_bytes() == (
        second / "classifier_results.json"
    ).read_bytes()
    assert (first / "oof_predictions.tsv").read_bytes() == (
        second / "oof_predictions.tsv"
    ).read_bytes()
    for artifact in (
        "classifier_diagnostics.json",
        "classifier_diagnostics.svg",
        "model.json",
        "model_card.json",
        "model_card.md",
        "inference_schema.json",
        "inference_example.tsv",
    ):
        assert (first / artifact).is_file()
    inference_schema = json.loads((first / "inference_schema.json").read_text())
    Draft202012Validator.check_schema(inference_schema)
    model_schema = json.loads((ROOT / "schemas/classifier_model.schema.json").read_text())
    Draft202012Validator(model_schema).validate(json.loads((first / "model.json").read_text()))
    prediction = predict_with_model(archive, first / "model.json", tmp_path / "prediction")
    assert prediction["sample_count"] == len(sample_ids)
    assert prediction["feature_overlap"]["overlap_fraction"] == 1.0
    assert {item["sample_id"] for item in prediction["predictions"]} == set(sample_ids)
    prediction_schema = json.loads(
        (ROOT / "schemas/classifier_prediction_results.schema.json").read_text()
    )
    Draft202012Validator(prediction_schema).validate(prediction)
    schema = json.loads((ROOT / "schemas/classifier_results.schema.json").read_text())
    Draft202012Validator(schema).validate(result)


def test_locked_classifier_inference_blocks_a_missing_required_feature(tmp_path: Path) -> None:
    archive = tmp_path / "bundle.tar.gz"
    _bundle(archive)
    model = tmp_path / "model.json"
    model.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "model_type": "binary_elastic_net_logistic_regression",
                "analysis_id": "analysis-1",
                "prepared_dataset_id": "prepared-1",
                "assay": "log_expression",
                "negative_class": "control",
                "positive_class": "treated",
                "selected_feature_ids": ["not_in_bundle"],
                "preprocessing": {"means": [0.0], "scales": [1.0]},
                "estimator": {"coefficients": [1.0], "intercept": 0.0},
                "calibration": {"method": "none", "coefficient": None, "intercept": None},
                "decision_threshold": 0.5,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"required model feature.*missing"):
        predict_with_model(archive, model, tmp_path / "prediction")


def test_locked_classifier_inference_rejects_manifest_asset_change(tmp_path: Path) -> None:
    archive = tmp_path / "bundle.tar.gz"
    _bundle(archive)
    model = tmp_path / "model.json"
    payload = {
        "schema_version": "1.0.0",
        "model_type": "binary_elastic_net_logistic_regression",
        "analysis_id": "analysis-1",
        "prepared_dataset_id": "prepared-1",
        "assay": "log_expression",
        "negative_class": "control",
        "positive_class": "treated",
        "selected_feature_ids": ["gene_0000"],
        "preprocessing": {"means": [0.0], "scales": [1.0]},
        "estimator": {"coefficients": [1.0], "intercept": 0.0},
        "calibration": {"method": "none", "coefficient": None, "intercept": None},
        "decision_threshold": 0.5,
    }
    model.write_text(json.dumps(payload), encoding="utf-8")
    manifest = tmp_path / "model_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "status": "LOCKED",
                "serialized_model": {"sha256": "0" * 64},
                "ordered_feature_schema": payload["selected_feature_ids"],
                "expected_assay": "log_expression",
                "checksums": {
                    "feature_schema": hashlib.sha256(
                        json.dumps(payload["selected_feature_ids"], separators=(",", ":")).encode()
                    ).hexdigest(),
                    "preprocessing": hashlib.sha256(
                        json.dumps(
                            payload["preprocessing"],
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest(),
                    "decision_rule": "0" * 64,
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="serialized model integrity"):
        predict_with_model(archive, model, tmp_path / "prediction", manifest)


def test_leakage_trap_rejects_an_intentionally_incorrect_fit_scope() -> None:
    correct = [
        {
            "preprocessing_fit_sample_ids": ["sample_1", "sample_2"],
            "outer_test_sample_ids": ["sample_3"],
        }
    ]
    validate_leakage_audit(correct)
    incorrect = [
        {
            "preprocessing_fit_sample_ids": ["sample_1", "sample_2", "sample_3"],
            "outer_test_sample_ids": ["sample_3"],
        }
    ]
    with pytest.raises(ValueError, match="preprocessing observed an outer test sample"):
        validate_leakage_audit(incorrect)


def test_permutation_control_shuffles_homogeneous_labels_between_groups() -> None:
    y = np.asarray([0, 0, 1, 1, 0, 0, 1, 1], dtype=np.int64)
    groups = np.asarray(["a", "a", "b", "b", "c", "c", "d", "d"], dtype=np.str_)
    permuted = _permuted_labels(y, groups, np.random.default_rng(7))

    assert not np.array_equal(permuted, y)
    assert all(len(set(permuted[groups == group].tolist())) == 1 for group in set(groups))
    assert Counter(permuted.tolist()) == Counter(y.tolist())
