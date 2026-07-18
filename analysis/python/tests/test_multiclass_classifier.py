"""Multiclass nested-CV and locked-model acceptance tests."""

import io
import json
import tarfile
from collections import Counter
from pathlib import Path

import numpy as np
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from sklearn.model_selection import StratifiedGroupKFold  # type: ignore[import-untyped]
from transcriptforge_analysis.classifier_prediction import predict_with_model
from transcriptforge_analysis.multiclass_classifier import (
    MulticlassConfig,
    run_multiclass_classifier,
)

ROOT = Path(__file__).parents[3]


def _bundle(path: Path) -> tuple[list[str], list[str], list[str]]:
    rng = np.random.default_rng(20260718)
    classes = ["basal", "luminal", "immune"]
    sample_ids = [f"subject_{subject:02d}_{label}" for subject in range(1, 13) for label in classes]
    outcomes = [label for _subject in range(1, 13) for label in classes]
    groups = [f"subject_{subject:02d}" for subject in range(1, 13) for _label in classes]
    matrix = rng.normal(0, 0.3, size=(45, len(sample_ids)))
    for class_index in range(3):
        mask = np.asarray([index == class_index for index in range(3)] * 12)
        matrix[class_index * 6 : (class_index + 1) * 6, mask] += 2.5
    assay_lines = ["feature_id\t" + "\t".join(sample_ids)]
    assay_lines.extend(
        f"gene_{index + 1:03d}\t" + "\t".join(f"{value:.8f}" for value in row)
        for index, row in enumerate(matrix)
    )
    metadata_lines = ["sample_id\tsubtype\tsubject_id\tcohort"]
    metadata_lines.extend(
        f"{sample_id}\t{outcome}\t{group}\tcohort_{'A' if index < 18 else 'B'}"
        for index, (sample_id, outcome, group) in enumerate(
            zip(sample_ids, outcomes, groups, strict=True)
        )
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


def _fold_plan(outcomes: list[str], groups: list[str]) -> list[dict[str, object]]:
    y = np.asarray(outcomes)
    group_array = np.asarray(groups)
    plan = []
    for repeat in range(2):
        splitter = StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=20260718 + repeat)
        for fold, (training, test) in enumerate(
            splitter.split(np.zeros((len(y), 1)), y, group_array), 1
        ):
            plan.append(
                {
                    "repeat": repeat + 1,
                    "fold": fold,
                    "training_sample_count": len(training),
                    "test_sample_count": len(test),
                    "training_class_counts": dict(Counter(y[training].tolist())),
                    "test_class_counts": dict(Counter(y[test].tolist())),
                    "training_group_count": len(set(group_array[training].tolist())),
                    "test_group_count": len(set(group_array[test].tolist())),
                    "group_overlap_count": 0,
                }
            )
    return plan


def test_multiclass_nested_cv_locks_a_deterministic_model(tmp_path: Path) -> None:
    archive = tmp_path / "bundle.tar.gz"
    sample_ids, outcomes, groups = _bundle(archive)
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "analysis_id": "multiclass-1",
                "prepared_dataset_id": "prepared-1",
                "analysis_type": "classifier",
                "method": "multinomial_elastic_net",
                "assay": "log_expression",
                "parameters": {
                    "outcome_column": "subtype",
                    "positive_class": None,
                    "group_column": "subject_id",
                    "cohort_column": "cohort",
                    "validation_mode": "repeated_nested_cross_validation",
                    "feature_filter": "top_variance",
                    "top_variable_features": 18,
                    "class_weight": "balanced",
                    "outer_folds": 3,
                    "inner_folds": 2,
                    "repeats": 2,
                    "primary_metric": "macro_roc_auc",
                    "probability_calibration": "none",
                    "decision_threshold_strategy": "fixed_0_5",
                    "bootstrap_iterations": 200,
                    "permutation_count": 2,
                },
                "random_seed": 20260718,
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
    Draft202012Validator(
        json.loads((ROOT / "schemas/analysis_request.schema.json").read_text())
    ).validate(json.loads(request.read_text()))
    first = tmp_path / "first"
    second = tmp_path / "second"
    result = run_multiclass_classifier(archive, MulticlassConfig.from_json(request), first)
    run_multiclass_classifier(archive, MulticlassConfig.from_json(request), second)

    assert result["metrics"]["macro_roc_auc"] > 0.98
    assert result["metrics"]["macro_f1"] > 0.9
    assert result["oof_coverage"]["observed_prediction_count"] == len(sample_ids) * 2
    assert all(fold["group_overlap_count"] == 0 for fold in result["folds"])
    assert all(
        abs(sum(item["class_probabilities"].values()) - 1.0) < 1e-9
        for item in result["oof_predictions"]
    )
    assert result["permutation_control"]["count"] == 2
    assert (first / "classifier_results.json").read_bytes() == (
        second / "classifier_results.json"
    ).read_bytes()
    Draft202012Validator(
        json.loads((ROOT / "schemas/multiclass_classifier_results.schema.json").read_text())
    ).validate(result)
    Draft202012Validator(
        json.loads((ROOT / "schemas/multiclass_classifier_model.schema.json").read_text())
    ).validate(json.loads((first / "model.json").read_text()))
    prediction = predict_with_model(archive, first / "model.json", tmp_path / "prediction")
    assert prediction["classes"] == ["basal", "immune", "luminal"]
    assert all(
        abs(sum(item["class_probabilities"].values()) - 1.0) < 1e-9
        for item in prediction["predictions"]
    )
    Draft202012Validator(
        json.loads(
            (ROOT / "schemas/multiclass_classifier_prediction_results.schema.json").read_text()
        )
    ).validate(prediction)
