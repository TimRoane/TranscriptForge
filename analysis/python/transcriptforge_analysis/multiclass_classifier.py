"""Leakage-resistant multinomial elastic-net classification."""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import warnings
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import sklearn  # type: ignore[import-untyped]
from numpy.typing import NDArray
from sklearn.exceptions import ConvergenceWarning  # type: ignore[import-untyped]
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
from sklearn.metrics import (  # type: ignore[import-untyped]
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
    roc_auc_score,
    roc_curve,
)

from transcriptforge_analysis.classifier import _digest_ids, _permuted_labels, _split
from transcriptforge_analysis.matrix_validation import write_json_atomic
from transcriptforge_analysis.pca import load_bundle_assay
from transcriptforge_analysis.reporting import write_dimension_reduction_report

MulticlassMetric = Literal["macro_roc_auc", "macro_f1", "balanced_accuracy"]


@dataclass(frozen=True, slots=True)
class MulticlassConfig:
    analysis_id: str
    prepared_dataset_id: str
    assay: str
    outcome_column: str
    group_column: str | None
    cohort_column: str | None
    top_variable_features: int
    class_weight: Literal["none", "balanced"]
    outer_folds: int
    inner_folds: int
    repeats: int
    primary_metric: MulticlassMetric
    bootstrap_iterations: int
    permutation_count: int
    random_seed: int
    frozen_fold_plan: tuple[dict[str, Any], ...]

    @classmethod
    def from_json(cls, path: Path) -> MulticlassConfig:
        payload = json.loads(path.read_text(encoding="utf-8"))
        parameters = payload.get("parameters", {})
        validation = payload.get("design_validation", {})
        if payload.get("analysis_type") != "classifier":
            raise ValueError("Multiclass runner requires analysis_type 'classifier'.")
        if payload.get("method") != "multinomial_elastic_net":
            raise ValueError("Multiclass runner requires method 'multinomial_elastic_net'.")
        if payload.get("assay") != "log_expression":
            raise ValueError("Multiclass runner requires the log_expression assay.")
        if parameters.get("positive_class") is not None:
            raise ValueError("Multiclass classification does not define a positive class.")
        if parameters.get("probability_calibration") != "none":
            raise ValueError("Multiclass v1 does not apply probability calibration.")
        if parameters.get("decision_threshold_strategy") != "fixed_0_5":
            raise ValueError("Multiclass v1 uses argmax classification without a binary threshold.")
        if not validation.get("valid") or not validation.get("fold_plan"):
            raise ValueError("A valid frozen multiclass fold plan is required.")
        return cls(
            analysis_id=str(payload["analysis_id"]),
            prepared_dataset_id=str(payload["prepared_dataset_id"]),
            assay="log_expression",
            outcome_column=str(parameters["outcome_column"]),
            group_column=str(parameters["group_column"])
            if parameters.get("group_column")
            else None,
            cohort_column=(
                str(parameters["cohort_column"]) if parameters.get("cohort_column") else None
            ),
            top_variable_features=int(parameters["top_variable_features"]),
            class_weight=cast(Literal["none", "balanced"], parameters["class_weight"]),
            outer_folds=int(parameters["outer_folds"]),
            inner_folds=int(parameters["inner_folds"]),
            repeats=int(parameters["repeats"]),
            primary_metric=cast(MulticlassMetric, parameters["primary_metric"]),
            bootstrap_iterations=int(parameters["bootstrap_iterations"]),
            permutation_count=int(parameters["permutation_count"]),
            random_seed=int(payload["random_seed"]),
            frozen_fold_plan=tuple(dict(item) for item in validation["fold_plan"]),
        )


@dataclass(frozen=True, slots=True)
class MulticlassFoldModel:
    feature_indices: NDArray[np.int64]
    means: NDArray[np.float64]
    scales: NDArray[np.float64]
    model: LogisticRegression

    def probabilities(self, matrix: NDArray[np.float64]) -> NDArray[np.float64]:
        transformed = (matrix[:, self.feature_indices] - self.means) / self.scales
        return cast(NDArray[np.float64], self.model.predict_proba(transformed))


def run_multiclass_classifier(
    bundle_archive: Path, config: MulticlassConfig, output_dir: Path
) -> dict[str, Any]:
    bundle = load_bundle_assay(bundle_archive, config.assay)
    output_dir.mkdir(parents=True, exist_ok=False)
    matrix = np.asarray(bundle.matrix.T, dtype=np.float64)
    if not np.all(np.isfinite(matrix)):
        raise ValueError("Multiclass classifier input contains non-finite expression values.")
    outcomes = _metadata_values(bundle.sample_ids, bundle.metadata, config.outcome_column)
    classes = sorted(set(outcomes))
    if not 3 <= len(classes) <= 20:
        raise ValueError("The frozen multiclass outcome must contain between 3 and 20 levels.")
    class_index = {label: index for index, label in enumerate(classes)}
    y = np.asarray([class_index[value] for value in outcomes], dtype=np.int64)
    groups = (
        np.asarray(
            _metadata_values(bundle.sample_ids, bundle.metadata, config.group_column), dtype=np.str_
        )
        if config.group_column
        else None
    )
    cohorts = (
        _metadata_values(bundle.sample_ids, bundle.metadata, config.cohort_column)
        if config.cohort_column
        else [""] * len(bundle.sample_ids)
    )
    feature_count = min(config.top_variable_features, matrix.shape[1])
    predictions: list[dict[str, Any]] = []
    folds: list[dict[str, Any]] = []
    feature_records: dict[tuple[str, str], dict[str, Any]] = {}
    for repeat in range(config.repeats):
        outer = _split(y, groups, config.outer_folds, config.random_seed + repeat)
        for fold_index, (training, test) in enumerate(outer, 1):
            inner_seed = config.random_seed + 10_000 + repeat * config.outer_folds + fold_index
            inner = _split(
                y[training],
                groups[training] if groups is not None else None,
                config.inner_folds,
                inner_seed,
            )
            best = _tune(
                matrix[training],
                y[training],
                inner,
                feature_count,
                config,
                inner_seed,
                len(classes),
            )
            fitted = _fit_model(
                matrix[training],
                y[training],
                feature_count,
                best[0],
                best[1],
                config,
                config.random_seed + repeat * 100 + fold_index,
            )
            probabilities = fitted.probabilities(matrix[test])
            predicted = np.argmax(probabilities, axis=1)
            selected_ids = [bundle.feature_ids[index] for index in fitted.feature_indices]
            coefficients = cast(NDArray[np.float64], fitted.model.coef_)
            for class_position, label in enumerate(classes):
                for feature_id, coefficient in zip(
                    selected_ids, coefficients[class_position], strict=True
                ):
                    record = feature_records.setdefault(
                        (feature_id, label),
                        {
                            "feature_id": feature_id,
                            "class_label": label,
                            "selected_folds": 0,
                            "nonzero_folds": 0,
                            "coefficients": [],
                        },
                    )
                    record["selected_folds"] += 1
                    record["nonzero_folds"] += int(abs(float(coefficient)) > 1e-12)
                    record["coefficients"].append(float(coefficient))
            train_ids = [bundle.sample_ids[index] for index in training]
            test_ids = [bundle.sample_ids[index] for index in test]
            overlap = (
                len(set(groups[training].tolist()) & set(groups[test].tolist()))
                if groups is not None
                else 0
            )
            folds.append(
                {
                    "repeat": repeat + 1,
                    "fold": fold_index,
                    "training_sample_count": len(training),
                    "test_sample_count": len(test),
                    "training_class_counts": _class_counts(y[training], classes),
                    "test_class_counts": _class_counts(y[test], classes),
                    "training_group_count": len(set(groups[training].tolist()))
                    if groups is not None
                    else len(training),
                    "test_group_count": len(set(groups[test].tolist()))
                    if groups is not None
                    else len(test),
                    "group_overlap_count": overlap,
                    "selected_feature_count": len(selected_ids),
                    "nonzero_coefficient_count": int(np.sum(np.abs(coefficients) > 1e-12)),
                    "best_c": best[0],
                    "best_l1_ratio": best[1],
                    "preprocessing_fit_sample_ids_sha256": _digest_ids(train_ids),
                    "outer_test_sample_ids_sha256": _digest_ids(test_ids),
                }
            )
            for local, sample_index in enumerate(test):
                predictions.append(
                    {
                        "sample_id": bundle.sample_ids[sample_index],
                        "repeat": repeat + 1,
                        "fold": fold_index,
                        "observed_class": outcomes[sample_index],
                        "predicted_class": classes[int(predicted[local])],
                        "class_probabilities": {
                            label: float(probabilities[local, index])
                            for index, label in enumerate(classes)
                        },
                        "group": groups[sample_index] if groups is not None else None,
                        "cohort": cohorts[sample_index] if config.cohort_column else None,
                    }
                )
    _validate_fold_plan(folds, config.frozen_fold_plan)
    _validate_oof(predictions, bundle.sample_ids, config.repeats)
    metrics = _prediction_metrics(predictions, classes)
    repeat_metrics = [
        {
            "repeat": repeat,
            **_prediction_metrics(
                [item for item in predictions if item["repeat"] == repeat], classes
            ),
        }
        for repeat in range(1, config.repeats + 1)
    ]
    confidence_intervals = _bootstrap_intervals(
        predictions, classes, config.bootstrap_iterations, config.random_seed
    )
    diagnostics = _diagnostics(predictions, classes)
    permutation = _permutation_control(
        matrix, y, groups, classes, config, feature_count, float(metrics["macro_roc_auc"])
    )
    total_folds = config.outer_folds * config.repeats
    feature_stability = sorted(
        (
            {
                "feature_id": item["feature_id"],
                "class_label": item["class_label"],
                "selection_frequency": item["selected_folds"] / total_folds,
                "nonzero_frequency": item["nonzero_folds"] / total_folds,
                "mean_coefficient": float(np.mean(item["coefficients"])),
            }
            for item in feature_records.values()
        ),
        key=lambda item: (-abs(float(item["mean_coefficient"])), str(item["feature_id"])),
    )
    locked_model = _fit_locked_model(
        matrix, y, groups, bundle.feature_ids, classes, config, feature_count
    )
    result = {
        "schema_version": "1.0.0",
        "analysis_id": config.analysis_id,
        "prepared_dataset_id": config.prepared_dataset_id,
        "method": "multinomial_elastic_net",
        "assay": config.assay,
        "outcome": {
            "column": config.outcome_column,
            "classes": classes,
            "class_counts": _class_counts(y, classes),
        },
        "validation": {
            "mode": "repeated_nested_cross_validation",
            "group_column": config.group_column,
            "cohort_column": config.cohort_column,
            "outer_folds": config.outer_folds,
            "inner_folds": config.inner_folds,
            "repeats": config.repeats,
            "primary_metric": config.primary_metric,
            "prediction_rule": "maximum_class_probability",
        },
        "sample_count": len(bundle.sample_ids),
        "input_feature_count": len(bundle.feature_ids),
        "top_variable_features": feature_count,
        "oof_coverage": {
            "expected_prediction_count": len(bundle.sample_ids) * config.repeats,
            "observed_prediction_count": len(predictions),
            "one_prediction_per_sample_per_repeat": True,
        },
        "metrics": metrics,
        "repeat_metrics": repeat_metrics,
        "confidence_intervals": confidence_intervals,
        "diagnostics": diagnostics,
        "permutation_control": permutation,
        "folds": folds,
        "oof_predictions": predictions,
        "feature_stability": feature_stability,
        "leakage_audit": {
            "preprocessing_scope": "fit_inside_each_training_fold",
            "feature_selection_scope": "fit_inside_each_training_fold",
            "hyperparameter_tuning_scope": "inner_training_folds_only",
            "outer_test_fold_role": "evaluation_only",
            "all_fold_scopes_disjoint": True,
        },
        "provenance": {
            "expression_bundle_sha256": hashlib.sha256(bundle_archive.read_bytes()).hexdigest(),
            "random_seed": config.random_seed,
        },
        "locked_model": {
            "path": "model.json",
            "feature_schema_path": "inference_schema.json",
            "model_card_path": "model_card.json",
            "inference_example_path": "inference_example.tsv",
        },
        "warnings": [
            "Performance is internal validation, not external or clinical validation.",
            "Multiclass probabilities are uncalibrated and classification uses argmax.",
        ],
        "software": {
            "language": "Python",
            "language_version": platform.python_version(),
            "implementation": "transcriptforge_analysis.multiclass_classifier",
            "packages": {"numpy": np.__version__, "scikit-learn": sklearn.__version__},
        },
    }
    _write_outputs(output_dir, result, locked_model, diagnostics)
    return result


def _fit_model(
    matrix: NDArray[np.float64],
    y: NDArray[np.int64],
    feature_count: int,
    c_value: float,
    l1_ratio: float,
    config: MulticlassConfig,
    seed: int,
) -> MulticlassFoldModel:
    variances = np.var(matrix, axis=0, ddof=1)
    selected = np.asarray(
        np.lexsort((np.arange(matrix.shape[1]), -variances))[:feature_count], dtype=np.int64
    )
    means = np.mean(matrix[:, selected], axis=0)
    scales = np.std(matrix[:, selected], axis=0, ddof=0)
    scales[scales == 0] = 1.0
    transformed = (matrix[:, selected] - means) / scales
    model = LogisticRegression(
        penalty="elasticnet",
        solver="saga",
        C=c_value,
        l1_ratio=l1_ratio,
        class_weight="balanced" if config.class_weight == "balanced" else None,
        max_iter=20_000,
        tol=1e-4,
        random_state=seed,
    )
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")
        warnings.simplefilter("error", ConvergenceWarning)
        model.fit(transformed, y)
    return MulticlassFoldModel(selected, means, scales, model)


def _tune(
    matrix: NDArray[np.float64],
    y: NDArray[np.int64],
    splits: list[tuple[NDArray[np.int64], NDArray[np.int64]]],
    feature_count: int,
    config: MulticlassConfig,
    seed: int,
    class_count: int,
) -> tuple[float, float]:
    candidates = [(c, ratio) for c in (0.05, 0.5, 5.0) for ratio in (0.0, 0.5, 1.0)]
    best, best_score = candidates[0], -np.inf
    for candidate_index, candidate in enumerate(candidates):
        probabilities = np.full((len(y), class_count), np.nan, dtype=np.float64)
        for inner_fold, (training, validation) in enumerate(splits):
            fitted = _fit_model(
                matrix[training],
                y[training],
                feature_count,
                candidate[0],
                candidate[1],
                config,
                seed + candidate_index * 100 + inner_fold,
            )
            probabilities[validation] = fitted.probabilities(matrix[validation])
        if np.any(~np.isfinite(probabilities)):
            raise ValueError("Multiclass inner tuning did not predict every training sample.")
        score = _primary_score(y, probabilities, config.primary_metric)
        if score > best_score + 1e-12:
            best, best_score = candidate, score
    return best


def _primary_score(
    y: NDArray[np.int64], probabilities: NDArray[np.float64], metric: MulticlassMetric
) -> float:
    if metric == "macro_roc_auc":
        return float(roc_auc_score(y, probabilities, multi_class="ovr", average="macro"))
    predicted = np.argmax(probabilities, axis=1)
    if metric == "macro_f1":
        return float(f1_score(y, predicted, average="macro"))
    return float(balanced_accuracy_score(y, predicted))


def _array_metrics(y: NDArray[np.int64], probabilities: NDArray[np.float64]) -> dict[str, float]:
    predicted = np.argmax(probabilities, axis=1)
    return {
        "macro_roc_auc": float(roc_auc_score(y, probabilities, multi_class="ovr", average="macro")),
        "macro_f1": float(f1_score(y, predicted, average="macro")),
        "balanced_accuracy": float(balanced_accuracy_score(y, predicted)),
        "accuracy": float(accuracy_score(y, predicted)),
        "log_loss": float(log_loss(y, probabilities, labels=np.arange(probabilities.shape[1]))),
    }


def _prediction_arrays(
    predictions: list[dict[str, Any]], classes: list[str]
) -> tuple[NDArray[np.int64], NDArray[np.float64]]:
    lookup = {label: index for index, label in enumerate(classes)}
    y = np.asarray([lookup[str(item["observed_class"])] for item in predictions], dtype=np.int64)
    probabilities = np.asarray(
        [[item["class_probabilities"][label] for label in classes] for item in predictions],
        dtype=np.float64,
    )
    return y, probabilities


def _prediction_metrics(predictions: list[dict[str, Any]], classes: list[str]) -> dict[str, float]:
    return _array_metrics(*_prediction_arrays(predictions, classes))


def _bootstrap_intervals(
    predictions: list[dict[str, Any]], classes: list[str], iterations: int, seed: int
) -> dict[str, Any]:
    rows_by_sample: dict[str, list[dict[str, Any]]] = {}
    for item in predictions:
        rows_by_sample.setdefault(str(item["sample_id"]), []).append(item)
    lookup = {label: index for index, label in enumerate(classes)}
    rows = [
        {
            "group": sample_rows[0]["group"] or sample_id,
            "y": lookup[str(sample_rows[0]["observed_class"])],
            "probabilities": np.mean(
                [[item["class_probabilities"][label] for label in classes] for item in sample_rows],
                axis=0,
            ),
        }
        for sample_id, sample_rows in sorted(rows_by_sample.items())
    ]
    by_group: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        by_group.setdefault(str(row["group"]), []).append(index)
    group_ids = sorted(by_group)
    distributions: dict[str, list[float]] = {
        name: []
        for name in _array_metrics(
            np.arange(len(classes), dtype=np.int64), np.eye(len(classes), dtype=np.float64)
        )
    }
    rng = np.random.default_rng(seed + 70_000)
    attempts = 0
    while len(distributions["macro_roc_auc"]) < iterations and attempts < iterations * 30:
        attempts += 1
        sampled = rng.choice(group_ids, size=len(group_ids), replace=True)
        indices = [index for group in sampled for index in by_group[str(group)]]
        y = np.asarray([rows[index]["y"] for index in indices], dtype=np.int64)
        if len(set(y.tolist())) != len(classes):
            continue
        probabilities = np.asarray([rows[index]["probabilities"] for index in indices])
        for name, value in _array_metrics(y, probabilities).items():
            distributions[name].append(value)
    if len(distributions["macro_roc_auc"]) != iterations:
        raise ValueError("Multiclass group bootstrap could not produce valid resamples.")
    return {
        "method": "experimental_unit_percentile_bootstrap",
        "iterations": iterations,
        "confidence_level": 0.95,
        "intervals": {
            name: {
                "lower": float(np.quantile(values, 0.025)),
                "upper": float(np.quantile(values, 0.975)),
            }
            for name, values in distributions.items()
        },
    }


def _diagnostics(predictions: list[dict[str, Any]], classes: list[str]) -> dict[str, Any]:
    y, probabilities = _prediction_arrays(predictions, classes)
    predicted = np.argmax(probabilities, axis=1)
    return {
        "one_vs_rest_roc_curves": {
            label: [
                {"false_positive_rate": float(x), "true_positive_rate": float(y_value)}
                for x, y_value in zip(
                    *roc_curve((y == index).astype(np.int64), probabilities[:, index])[:2],
                    strict=True,
                )
            ]
            for index, label in enumerate(classes)
        },
        "confusion_matrix": confusion_matrix(y, predicted, labels=np.arange(len(classes))).tolist(),
        "class_order": classes,
    }


def _permutation_control(
    matrix: NDArray[np.float64],
    y: NDArray[np.int64],
    groups: NDArray[np.str_] | None,
    classes: list[str],
    config: MulticlassConfig,
    feature_count: int,
    observed_auc: float,
) -> dict[str, Any]:
    rng = np.random.default_rng(config.random_seed + 80_000)
    values = []
    for permutation in range(config.permutation_count):
        permuted = _permuted_labels(y, groups, rng)
        all_y: list[int] = []
        all_probabilities: list[list[float]] = []
        for repeat in range(config.repeats):
            outer = _split(y, groups, config.outer_folds, config.random_seed + repeat)
            for fold_index, (training, test) in enumerate(outer):
                inner_seed = config.random_seed + 90_000 + permutation * 10_000 + fold_index
                inner = _split(
                    permuted[training],
                    groups[training] if groups is not None else None,
                    config.inner_folds,
                    inner_seed,
                )
                best = _tune(
                    matrix[training],
                    permuted[training],
                    inner,
                    feature_count,
                    config,
                    inner_seed,
                    len(classes),
                )
                fitted = _fit_model(
                    matrix[training],
                    permuted[training],
                    feature_count,
                    best[0],
                    best[1],
                    config,
                    inner_seed + 5_000,
                )
                all_y.extend(permuted[test].tolist())
                all_probabilities.extend(fitted.probabilities(matrix[test]).tolist())
        values.append(
            float(
                roc_auc_score(
                    np.asarray(all_y),
                    np.asarray(all_probabilities),
                    multi_class="ovr",
                    average="macro",
                )
            )
        )
    return {
        "method": "full_nested_cross_validation_label_permutation",
        "count": config.permutation_count,
        "macro_roc_auc_values": values,
        "mean_macro_roc_auc": float(np.mean(values)) if values else None,
        "empirical_p_value": (
            (1 + sum(value >= observed_auc for value in values)) / (len(values) + 1)
            if values
            else None
        ),
    }


def _fit_locked_model(
    matrix: NDArray[np.float64],
    y: NDArray[np.int64],
    groups: NDArray[np.str_] | None,
    feature_ids: list[str],
    classes: list[str],
    config: MulticlassConfig,
    feature_count: int,
) -> dict[str, Any]:
    inner = _split(y, groups, config.inner_folds, config.random_seed + 120_000)
    best = _tune(
        matrix, y, inner, feature_count, config, config.random_seed + 120_000, len(classes)
    )
    fitted = _fit_model(
        matrix, y, feature_count, best[0], best[1], config, config.random_seed + 130_000
    )
    return {
        "schema_version": "1.0.0",
        "model_type": "multiclass_elastic_net_logistic_regression",
        "analysis_id": config.analysis_id,
        "prepared_dataset_id": config.prepared_dataset_id,
        "assay": config.assay,
        "outcome_column": config.outcome_column,
        "classes": classes,
        "selected_feature_ids": [feature_ids[index] for index in fitted.feature_indices],
        "preprocessing": {
            "feature_filter": "top_variance_fit_on_complete_development_cohort_after_validation",
            "means": fitted.means.tolist(),
            "scales": fitted.scales.tolist(),
        },
        "estimator": {
            "c": best[0],
            "l1_ratio": best[1],
            "coefficients": cast(NDArray[np.float64], fitted.model.coef_).tolist(),
            "intercepts": cast(NDArray[np.float64], fitted.model.intercept_).tolist(),
        },
        "prediction_rule": "maximum_class_probability",
        "training": {
            "sample_count": len(y),
            "feature_count": matrix.shape[1],
            "random_seed": config.random_seed,
            "lock_scope": "complete_development_cohort_after_nested_cv",
        },
    }


def _inference_schema(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://transcriptforge.dev/schemas/model-inference-input/1.0.0",
        "title": "TranscriptForge locked multiclass classifier inference input",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "assay", "samples"],
        "properties": {
            "schema_version": {"const": "1.0.0"},
            "assay": {"const": model["assay"]},
            "samples": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["sample_id", "features"],
                    "properties": {
                        "sample_id": {"type": "string", "minLength": 1},
                        "features": {
                            "type": "object",
                            "required": model["selected_feature_ids"],
                            "additionalProperties": {"type": "number"},
                        },
                    },
                },
            },
        },
    }


def _write_outputs(
    output_dir: Path,
    result: dict[str, Any],
    model: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    write_json_atomic(output_dir / "classifier_results.json", result)
    write_json_atomic(output_dir / "classifier_diagnostics.json", diagnostics)
    write_json_atomic(output_dir / "model.json", model)
    write_json_atomic(output_dir / "inference_schema.json", _inference_schema(model))
    card = {
        "schema_version": "1.0.0",
        "model_name": "TranscriptForge multinomial elastic-net research classifier",
        "intended_use": (
            "Research-only multiclass hypothesis generation on compatible log-expression data."
        ),
        "prohibited_use": (
            "Clinical diagnosis, treatment selection, or deployment without independent validation."
        ),
        "development_data": {
            "prepared_dataset_id": result["prepared_dataset_id"],
            "sample_count": result["sample_count"],
            "outcome": result["outcome"],
        },
        "validation": {
            "type": "internal_grouped_repeated_nested_cross_validation",
            "metrics": result["metrics"],
            "confidence_intervals": result["confidence_intervals"],
            "permutation_control": result["permutation_control"],
            "external_validation_completed": False,
        },
        "limitations": result["warnings"],
    }
    write_json_atomic(output_dir / "model_card.json", card)
    (output_dir / "model_card.md").write_text(
        "# TranscriptForge multinomial elastic-net research classifier\n\n"
        + card["intended_use"]
        + "\n\n## Limitations\n\n"
        + "\n".join(f"- {item}" for item in card["limitations"])
        + "\n",
        encoding="utf-8",
    )
    selected = cast(list[str], model["selected_feature_ids"])
    (output_dir / "inference_example.tsv").write_text(
        "sample_id\t"
        + "\t".join(selected)
        + "\nexample_sample\t"
        + "\t".join("" for _ in selected)
        + "\n",
        encoding="utf-8",
    )
    _write_table(
        output_dir / "oof_predictions.tsv", result["oof_predictions"], result["outcome"]["classes"]
    )
    _write_features(output_dir / "feature_stability.tsv", result["feature_stability"])
    write_json_atomic(output_dir / "result_manifest.json", _result_manifest(result))
    write_dimension_reduction_report(
        output_dir,
        title="Multinomial elastic-net classifier",
        analysis_id=result["analysis_id"],
        assay=result["assay"],
        summary={
            "Samples": result["sample_count"],
            "Classes": len(result["outcome"]["classes"]),
            "Macro ROC-AUC": f"{result['metrics']['macro_roc_auc']:.3f}",
            "Macro F1": f"{result['metrics']['macro_f1']:.3f}",
        },
        images=(),
        notes=tuple(result["warnings"]),
    )


def _write_table(path: Path, rows: list[dict[str, Any]], classes: list[str]) -> None:
    fields = [
        "sample_id",
        "repeat",
        "fold",
        "observed_class",
        "predicted_class",
        "group",
        "cohort",
    ] + [f"probability_{label}" for label in classes]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for row in rows:
            flat = {key: row[key] for key in fields if key in row}
            flat.update(
                {f"probability_{label}": row["class_probabilities"][label] for label in classes}
            )
            writer.writerow(flat)


def _write_features(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "feature_id",
        "class_label",
        "selection_frequency",
        "nonzero_frequency",
        "mean_coefficient",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _result_manifest(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "analysis_type": "classifier",
        "title": "Multinomial elastic-net classifier",
        "summary_metrics": [
            {"label": "Samples", "value": result["sample_count"]},
            {"label": "Classes", "value": len(result["outcome"]["classes"])},
            {"label": "Macro ROC-AUC", "value": result["metrics"]["macro_roc_auc"]},
            {"label": "Macro F1", "value": result["metrics"]["macro_f1"]},
        ],
        "sections": [
            {
                "id": "validation",
                "title": "Internal multiclass validation",
                "items": [
                    {"type": "file", "title": "Diagnostics", "path": "classifier_diagnostics.json"},
                    {"type": "table", "title": "OOF predictions", "path": "oof_predictions.tsv"},
                    {
                        "type": "table",
                        "title": "Feature stability",
                        "path": "feature_stability.tsv",
                    },
                ],
            },
            {
                "id": "locked-model",
                "title": "Locked research model",
                "items": [
                    {"type": "file", "title": "Model card", "path": "model_card.json"},
                    {"type": "file", "title": "Inference schema", "path": "inference_schema.json"},
                ],
            },
        ],
        "downloads": [
            {
                "type": "file",
                "title": "Structured classifier results",
                "path": "classifier_results.json",
            },
            {"type": "table", "title": "OOF predictions", "path": "oof_predictions.tsv"},
            {"type": "table", "title": "Feature stability", "path": "feature_stability.tsv"},
            {"type": "file", "title": "Locked model", "path": "model.json"},
            {"type": "file", "title": "Model card", "path": "model_card.json"},
            {"type": "file", "title": "Inference schema", "path": "inference_schema.json"},
        ],
        "warnings": result["warnings"],
    }


def _metadata_values(
    sample_ids: list[str], metadata: dict[str, dict[str, str]], column: str | None
) -> list[str]:
    if column is None:
        return []
    try:
        values = [metadata[sample_id][column].strip() for sample_id in sample_ids]
    except KeyError as error:
        raise ValueError(f"Multiclass metadata column '{column}' is missing.") from error
    if any(not value for value in values):
        raise ValueError(f"Multiclass metadata column '{column}' contains missing values.")
    return values


def _class_counts(y: NDArray[np.int64], classes: list[str]) -> dict[str, int]:
    counts = Counter(y.tolist())
    return {label: counts[index] for index, label in enumerate(classes)}


def _validate_oof(predictions: list[dict[str, Any]], sample_ids: list[str], repeats: int) -> None:
    counts = Counter((item["sample_id"], item["repeat"]) for item in predictions)
    expected = {(sample_id, repeat) for sample_id in sample_ids for repeat in range(1, repeats + 1)}
    if set(counts) != expected or any(value != 1 for value in counts.values()):
        raise ValueError(
            "Multiclass OOF coverage must contain one prediction per sample per repeat."
        )


def _validate_fold_plan(folds: list[dict[str, Any]], frozen: tuple[dict[str, Any], ...]) -> None:
    fields = (
        "repeat",
        "fold",
        "training_sample_count",
        "test_sample_count",
        "training_class_counts",
        "test_class_counts",
        "training_group_count",
        "test_group_count",
        "group_overlap_count",
    )
    if [{field: item[field] for field in fields} for item in folds] != [
        {field: item[field] for field in fields} for item in frozen
    ]:
        raise ValueError("Multiclass scientific splits differ from the frozen server audit.")
