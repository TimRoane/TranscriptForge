"""Leakage-resistant binary elastic-net classification over an Expression Bundle."""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import sys
import warnings
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import sklearn  # type: ignore[import-untyped]
from joblib import Parallel, delayed, parallel_config  # type: ignore[import-untyped]
from numpy.typing import NDArray
from sklearn.ensemble import (  # type: ignore[import-untyped]
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.exceptions import ConvergenceWarning  # type: ignore[import-untyped]
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
from sklearn.metrics import (  # type: ignore[import-untyped]
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    matthews_corrcoef,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import (  # type: ignore[import-untyped]
    StratifiedGroupKFold,
    StratifiedKFold,
)

from transcriptforge_analysis.matrix_validation import write_json_atomic
from transcriptforge_analysis.pca import load_bundle_assay
from transcriptforge_analysis.reporting import write_dimension_reduction_report

Metric = Literal["roc_auc", "pr_auc", "balanced_accuracy"]


@dataclass(frozen=True, slots=True)
class ClassifierConfig:
    analysis_id: str
    prepared_dataset_id: str
    assay: str
    outcome_column: str
    positive_class: str
    group_column: str | None
    cohort_column: str | None
    top_variable_features: int
    class_weight: Literal["none", "balanced"]
    outer_folds: int
    inner_folds: int
    repeats: int
    primary_metric: Metric
    probability_calibration: Literal["none", "sigmoid"]
    decision_threshold_strategy: Literal["fixed_0_5", "inner_cv_youden"]
    bootstrap_iterations: int
    permutation_count: int
    random_seed: int
    frozen_fold_plan: tuple[dict[str, Any], ...]

    @classmethod
    def from_json(cls, path: Path) -> ClassifierConfig:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("analysis_type") != "classifier":
            raise ValueError("Classifier runner requires analysis_type 'classifier'.")
        if payload.get("method") != "elastic_net":
            raise ValueError("Classifier runner only supports elastic_net.")
        if payload.get("assay") != "log_expression":
            raise ValueError("Classifier runner requires the log_expression assay.")
        parameters = payload.get("parameters", {})
        validation = payload.get("design_validation", {})
        if not validation.get("valid") or not validation.get("fold_plan"):
            raise ValueError("A valid frozen classifier fold plan is required.")
        return cls(
            analysis_id=str(payload["analysis_id"]),
            prepared_dataset_id=str(payload["prepared_dataset_id"]),
            assay="log_expression",
            outcome_column=str(parameters["outcome_column"]),
            positive_class=str(parameters["positive_class"]),
            group_column=(
                str(parameters["group_column"]) if parameters.get("group_column") else None
            ),
            cohort_column=(
                str(parameters["cohort_column"]) if parameters.get("cohort_column") else None
            ),
            top_variable_features=int(parameters["top_variable_features"]),
            class_weight=cast(Literal["none", "balanced"], parameters["class_weight"]),
            outer_folds=int(parameters["outer_folds"]),
            inner_folds=int(parameters["inner_folds"]),
            repeats=int(parameters["repeats"]),
            primary_metric=cast(Metric, parameters["primary_metric"]),
            probability_calibration=cast(
                Literal["none", "sigmoid"], parameters["probability_calibration"]
            ),
            decision_threshold_strategy=cast(
                Literal["fixed_0_5", "inner_cv_youden"],
                parameters["decision_threshold_strategy"],
            ),
            bootstrap_iterations=int(parameters["bootstrap_iterations"]),
            permutation_count=int(parameters["permutation_count"]),
            random_seed=int(payload["random_seed"]),
            frozen_fold_plan=tuple(dict(item) for item in validation["fold_plan"]),
        )


@dataclass(frozen=True, slots=True)
class FittedFoldModel:
    feature_indices: NDArray[np.int64]
    means: NDArray[np.float64]
    scales: NDArray[np.float64]
    model: LogisticRegression

    def decision_function(self, matrix: NDArray[np.float64]) -> NDArray[np.float64]:
        transformed = (matrix[:, self.feature_indices] - self.means) / self.scales
        return cast(NDArray[np.float64], self.model.decision_function(transformed))


def run_classifier(
    bundle_archive: Path,
    config: ClassifierConfig,
    output_dir: Path,
    *,
    permutation_workers: int = 1,
) -> dict[str, Any]:
    """Fit repeated grouped nested CV and publish complete OOF predictions."""
    bundle = load_bundle_assay(bundle_archive, config.assay)
    output_dir.mkdir(parents=True, exist_ok=False)
    matrix = np.asarray(bundle.matrix.T, dtype=np.float64)
    if not np.all(np.isfinite(matrix)):
        raise ValueError("Classifier input contains non-finite expression values.")
    outcomes = _metadata_values(bundle.sample_ids, bundle.metadata, config.outcome_column)
    levels = sorted(set(outcomes))
    if len(levels) != 2 or config.positive_class not in levels:
        raise ValueError("The frozen binary outcome no longer matches bundle metadata.")
    negative_class = next(item for item in levels if item != config.positive_class)
    y = np.asarray([int(item == config.positive_class) for item in outcomes], dtype=np.int64)
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
    feature_records: dict[str, dict[str, Any]] = {}
    for repeat_index in range(config.repeats):
        outer_splits = _split(y, groups, config.outer_folds, config.random_seed + repeat_index)
        for fold_index, (training, test) in enumerate(outer_splits, 1):
            _assert_disjoint_scope(training, test, "outer preprocessing")
            inner_seed = (
                config.random_seed + 10_000 + repeat_index * config.outer_folds + fold_index
            )
            inner_splits = _split(
                y[training],
                groups[training] if groups is not None else None,
                config.inner_folds,
                inner_seed,
            )
            best, inner_decisions = _tune(
                matrix[training],
                y[training],
                groups[training] if groups is not None else None,
                inner_splits,
                feature_count,
                config,
                inner_seed,
            )
            calibrator = _fit_calibrator(inner_decisions, y[training], config)
            inner_probabilities = _calibrate(inner_decisions, calibrator)
            threshold = (
                _youden_threshold(y[training], inner_probabilities)
                if config.decision_threshold_strategy == "inner_cv_youden"
                else 0.5
            )
            fitted = _fit_fold_model(
                matrix[training],
                y[training],
                feature_count,
                best[0],
                best[1],
                config,
                config.random_seed + repeat_index * 100 + fold_index,
            )
            probabilities = _calibrate(fitted.decision_function(matrix[test]), calibrator)
            predicted = probabilities >= threshold
            train_ids = [bundle.sample_ids[index] for index in training]
            test_ids = [bundle.sample_ids[index] for index in test]
            selected_features = [bundle.feature_ids[index] for index in fitted.feature_indices]
            coefficients = cast(NDArray[np.float64], fitted.model.coef_[0])
            for feature_id, coefficient in zip(selected_features, coefficients, strict=True):
                record = feature_records.setdefault(
                    feature_id,
                    {
                        "feature_id": feature_id,
                        "selected_folds": 0,
                        "nonzero_folds": 0,
                        "coefficients": [],
                    },
                )
                record["selected_folds"] += 1
                record["nonzero_folds"] += int(abs(float(coefficient)) > 1e-12)
                record["coefficients"].append(float(coefficient))
            overlap = (
                len(set(groups[training].tolist()) & set(groups[test].tolist()))
                if groups is not None
                else 0
            )
            fold_result = {
                "repeat": repeat_index + 1,
                "fold": fold_index,
                "training_sample_count": len(training),
                "test_sample_count": len(test),
                "training_class_counts": _class_counts(
                    y[training], negative_class, config.positive_class
                ),
                "test_class_counts": _class_counts(y[test], negative_class, config.positive_class),
                "training_group_count": len(set(groups[training].tolist()))
                if groups is not None
                else len(training),
                "test_group_count": len(set(groups[test].tolist()))
                if groups is not None
                else len(test),
                "group_overlap_count": overlap,
                "selected_feature_count": len(selected_features),
                "nonzero_feature_count": int(np.sum(np.abs(coefficients) > 1e-12)),
                "best_c": best[0],
                "best_l1_ratio": best[1],
                "decision_threshold": threshold,
                "preprocessing_fit_sample_ids_sha256": _digest_ids(train_ids),
                "outer_test_sample_ids_sha256": _digest_ids(test_ids),
            }
            folds.append(fold_result)
            for local_index, sample_index in enumerate(test):
                predictions.append(
                    {
                        "sample_id": bundle.sample_ids[sample_index],
                        "repeat": repeat_index + 1,
                        "fold": fold_index,
                        "observed_class": outcomes[sample_index],
                        "observed_positive": bool(y[sample_index]),
                        "positive_probability": float(probabilities[local_index]),
                        "predicted_positive": bool(predicted[local_index]),
                        "predicted_class": config.positive_class
                        if predicted[local_index]
                        else negative_class,
                        "group": groups[sample_index] if groups is not None else None,
                        "cohort": cohorts[sample_index] if config.cohort_column else None,
                    }
                )
    _validate_fold_plan(folds, config.frozen_fold_plan)
    _validate_oof_coverage(predictions, bundle.sample_ids, config.repeats)
    metrics = _metrics(predictions)
    repeat_metrics = [
        {"repeat": repeat, **_metrics([item for item in predictions if item["repeat"] == repeat])}
        for repeat in range(1, config.repeats + 1)
    ]
    confidence_intervals = _bootstrap_confidence_intervals(
        predictions, config.bootstrap_iterations, config.random_seed
    )
    diagnostics = _diagnostic_curves(predictions)
    permutation_control = _permutation_control(
        matrix,
        y,
        groups,
        config,
        feature_count,
        float(metrics["roc_auc"]),
        workers=permutation_workers,
    )
    learning_curve = _learning_curve(matrix, y, groups, folds, config, feature_count)
    model_comparisons = _comparison_models(matrix, y, groups, config, feature_count, metrics)
    locked_model = _fit_locked_model(
        matrix, y, groups, bundle.feature_ids, negative_class, config, feature_count
    )
    total_folds = config.outer_folds * config.repeats
    feature_stability = sorted(
        (
            {
                "feature_id": item["feature_id"],
                "selection_frequency": item["selected_folds"] / total_folds,
                "nonzero_frequency": item["nonzero_folds"] / total_folds,
                "mean_coefficient": float(np.mean(item["coefficients"])),
            }
            for item in feature_records.values()
        ),
        key=lambda item: (-abs(float(item["mean_coefficient"])), str(item["feature_id"])),
    )
    bundle_sha256 = hashlib.sha256(bundle_archive.read_bytes()).hexdigest()
    result = {
        "schema_version": "1.0.0",
        "analysis_id": config.analysis_id,
        "prepared_dataset_id": config.prepared_dataset_id,
        "method": "elastic_net",
        "assay": config.assay,
        "outcome": {
            "column": config.outcome_column,
            "negative_class": negative_class,
            "positive_class": config.positive_class,
            "class_counts": _class_counts(y, negative_class, config.positive_class),
        },
        "validation": {
            "mode": "repeated_nested_cross_validation",
            "group_column": config.group_column,
            "cohort_column": config.cohort_column,
            "outer_folds": config.outer_folds,
            "inner_folds": config.inner_folds,
            "repeats": config.repeats,
            "primary_metric": config.primary_metric,
            "probability_calibration": config.probability_calibration,
            "decision_threshold_strategy": config.decision_threshold_strategy,
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
        "diagnostic_curves": diagnostics,
        "permutation_control": permutation_control,
        "learning_curve": learning_curve,
        "model_comparisons": model_comparisons,
        "folds": folds,
        "oof_predictions": predictions,
        "feature_stability": feature_stability,
        "leakage_audit": {
            "preprocessing_scope": "fit_inside_each_training_fold",
            "feature_selection_scope": "fit_inside_each_training_fold",
            "hyperparameter_tuning_scope": "inner_training_folds_only",
            "calibration_scope": "inner_training_predictions_only",
            "threshold_scope": "inner_training_predictions_only",
            "outer_test_fold_role": "evaluation_only",
            "all_fold_scopes_disjoint": True,
        },
        "provenance": {
            "expression_bundle_sha256": bundle_sha256,
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
            "The locked final model is a research artifact and requires untouched external "
            "validation.",
        ],
        "software": {
            "language": "Python",
            "language_version": platform.python_version(),
            "implementation": "transcriptforge_analysis.classifier",
            "packages": {"numpy": np.__version__, "scikit-learn": sklearn.__version__},
        },
    }
    write_json_atomic(output_dir / "classifier_results.json", result)
    write_json_atomic(output_dir / "classifier_diagnostics.json", diagnostics)
    _write_predictions(output_dir / "oof_predictions.tsv", predictions)
    _write_features(output_dir / "feature_stability.tsv", feature_stability)
    write_json_atomic(output_dir / "model.json", locked_model)
    inference_schema = _inference_schema(locked_model)
    write_json_atomic(output_dir / "inference_schema.json", inference_schema)
    model_card = _model_card(result, locked_model)
    write_json_atomic(output_dir / "model_card.json", model_card)
    (output_dir / "model_card.md").write_text(_model_card_markdown(model_card), encoding="utf-8")
    _write_inference_example(output_dir / "inference_example.tsv", locked_model)
    _write_diagnostic_svg(output_dir / "classifier_diagnostics.svg", diagnostics, learning_curve)
    write_json_atomic(output_dir / "result_manifest.json", _result_manifest(result))
    write_dimension_reduction_report(
        output_dir,
        title="Binary elastic-net classifier",
        analysis_id=config.analysis_id,
        assay=config.assay,
        summary={
            "Samples": len(bundle.sample_ids),
            "Features": len(bundle.feature_ids),
            "Outer folds": config.outer_folds,
            "Repeats": config.repeats,
            "ROC-AUC": f"{metrics['roc_auc']:.3f}",
            "PR-AUC": f"{metrics['pr_auc']:.3f}",
        },
        images=(),
        notes=tuple(result["warnings"]),
    )
    return result


def _fit_fold_model(
    matrix: NDArray[np.float64],
    y: NDArray[np.int64],
    feature_count: int,
    c_value: float,
    l1_ratio: float,
    config: ClassifierConfig,
    seed: int,
) -> FittedFoldModel:
    variances = np.var(matrix, axis=0, ddof=1)
    order = np.lexsort((np.arange(matrix.shape[1]), -variances))[:feature_count]
    selected = np.asarray(order, dtype=np.int64)
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
    return FittedFoldModel(selected, means, scales, model)


def _tune(
    matrix: NDArray[np.float64],
    y: NDArray[np.int64],
    groups: NDArray[np.str_] | None,
    splits: list[tuple[NDArray[np.int64], NDArray[np.int64]]],
    feature_count: int,
    config: ClassifierConfig,
    seed: int,
) -> tuple[tuple[float, float], NDArray[np.float64]]:
    candidates = [(c, ratio) for c in (0.05, 0.5, 5.0) for ratio in (0.0, 0.5, 1.0)]
    best_candidate = candidates[0]
    best_score = -np.inf
    best_decisions = np.zeros(len(y), dtype=np.float64)
    for candidate_index, (c_value, l1_ratio) in enumerate(candidates):
        decisions = np.full(len(y), np.nan, dtype=np.float64)
        for inner_fold, (training, validation) in enumerate(splits):
            _assert_disjoint_scope(training, validation, "inner tuning")
            if groups is not None and set(groups[training].tolist()) & set(
                groups[validation].tolist()
            ):
                raise ValueError("Inner tuning leaks groups between training and validation.")
            fitted = _fit_fold_model(
                matrix[training],
                y[training],
                feature_count,
                c_value,
                l1_ratio,
                config,
                seed + candidate_index * 100 + inner_fold,
            )
            decisions[validation] = fitted.decision_function(matrix[validation])
        if np.any(~np.isfinite(decisions)):
            raise ValueError("Inner tuning did not produce one prediction per training sample.")
        score = _primary_score(y, _sigmoid(decisions), config.primary_metric)
        if score > best_score + 1e-12:
            best_score, best_candidate, best_decisions = score, (c_value, l1_ratio), decisions
    return best_candidate, best_decisions


def _fit_calibrator(
    decisions: NDArray[np.float64], y: NDArray[np.int64], config: ClassifierConfig
) -> LogisticRegression | None:
    if config.probability_calibration == "none":
        return None
    calibrator = LogisticRegression(C=1_000_000, solver="lbfgs", random_state=config.random_seed)
    calibrator.fit(decisions.reshape(-1, 1), y)
    return calibrator


def _calibrate(
    decisions: NDArray[np.float64], calibrator: LogisticRegression | None
) -> NDArray[np.float64]:
    if calibrator is None:
        return _sigmoid(decisions)
    return cast(NDArray[np.float64], calibrator.predict_proba(decisions.reshape(-1, 1))[:, 1])


def _sigmoid(values: NDArray[np.float64]) -> NDArray[np.float64]:
    clipped = np.clip(values, -709, 709)
    return 1.0 / (1.0 + np.exp(-clipped))


def _primary_score(
    y: NDArray[np.int64], probabilities: NDArray[np.float64], metric: Metric
) -> float:
    if metric == "roc_auc":
        return float(roc_auc_score(y, probabilities))
    if metric == "pr_auc":
        return float(average_precision_score(y, probabilities))
    return float(balanced_accuracy_score(y, probabilities >= 0.5))


def _youden_threshold(y: NDArray[np.int64], probabilities: NDArray[np.float64]) -> float:
    candidates = np.unique(np.concatenate(([0.0, 0.5, 1.0], probabilities)))
    scored = []
    for threshold in candidates:
        tn, fp, fn, tp = confusion_matrix(y, probabilities >= threshold, labels=[0, 1]).ravel()
        sensitivity = tp / max(tp + fn, 1)
        specificity = tn / max(tn + fp, 1)
        scored.append(
            (sensitivity + specificity - 1.0, -abs(float(threshold) - 0.5), float(threshold))
        )
    return max(scored)[2]


def _split(
    y: NDArray[np.int64],
    groups: NDArray[np.str_] | None,
    folds: int,
    seed: int,
) -> list[tuple[NDArray[np.int64], NDArray[np.int64]]]:
    placeholder = np.zeros((len(y), 1), dtype=np.float64)
    splitter = (
        StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
        if groups is None
        else StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    )
    source = (
        splitter.split(placeholder, y) if groups is None else splitter.split(placeholder, y, groups)
    )
    return [
        (np.asarray(train, dtype=np.int64), np.asarray(test, dtype=np.int64))
        for train, test in source
    ]


def _metrics(predictions: list[dict[str, Any]]) -> dict[str, float | int]:
    y = np.asarray([int(item["observed_positive"]) for item in predictions], dtype=np.int64)
    probabilities = np.asarray(
        [item["positive_probability"] for item in predictions], dtype=np.float64
    )
    predicted = np.asarray(
        [item["predicted_class"] == item["observed_class"] for item in predictions]
    )
    predicted_positive = np.asarray(
        [item["predicted_positive"] for item in predictions], dtype=np.bool_
    )
    tn, fp, fn, tp = confusion_matrix(y, predicted_positive, labels=[0, 1]).ravel()
    return {
        "roc_auc": float(roc_auc_score(y, probabilities)),
        "pr_auc": float(average_precision_score(y, probabilities)),
        "balanced_accuracy": float(balanced_accuracy_score(y, predicted_positive)),
        "accuracy": float(np.mean(predicted)),
        "sensitivity": float(tp / max(tp + fn, 1)),
        "specificity": float(tn / max(tn + fp, 1)),
        "precision": float(tp / max(tp + fp, 1)),
        "recall": float(tp / max(tp + fn, 1)),
        "f1": float(f1_score(y, predicted_positive)),
        "mcc": float(matthews_corrcoef(y, predicted_positive)),
        "brier_score": float(brier_score_loss(y, probabilities)),
        "true_positive": int(tp),
        "false_positive": int(fp),
        "true_negative": int(tn),
        "false_negative": int(fn),
    }


def _metrics_from_arrays(
    y: NDArray[np.int64], probabilities: NDArray[np.float64], predicted: NDArray[np.bool_]
) -> dict[str, float]:
    return {
        "roc_auc": float(roc_auc_score(y, probabilities)),
        "pr_auc": float(average_precision_score(y, probabilities)),
        "balanced_accuracy": float(balanced_accuracy_score(y, predicted)),
        "brier_score": float(brier_score_loss(y, probabilities)),
    }


def _bootstrap_confidence_intervals(
    predictions: list[dict[str, Any]], iterations: int, seed: int
) -> dict[str, Any]:
    by_sample: dict[str, list[dict[str, Any]]] = {}
    for item in predictions:
        by_sample.setdefault(str(item["sample_id"]), []).append(item)
    sample_rows = [
        {
            "sample_id": sample_id,
            "group": rows[0]["group"] or sample_id,
            "y": int(rows[0]["observed_positive"]),
            "probability": float(np.mean([row["positive_probability"] for row in rows])),
            "predicted": bool(np.mean([row["predicted_positive"] for row in rows]) >= 0.5),
        }
        for sample_id, rows in sorted(by_sample.items())
    ]
    by_group: dict[str, list[int]] = {}
    for index, row in enumerate(sample_rows):
        by_group.setdefault(str(row["group"]), []).append(index)
    group_ids = sorted(by_group)
    rng = np.random.default_rng(seed + 70_000)
    distributions: dict[str, list[float]] = {
        name: [] for name in ("roc_auc", "pr_auc", "balanced_accuracy", "brier_score")
    }
    attempts = 0
    while len(distributions["roc_auc"]) < iterations and attempts < iterations * 20:
        attempts += 1
        sampled_groups = rng.choice(group_ids, size=len(group_ids), replace=True)
        indices = [index for group in sampled_groups for index in by_group[str(group)]]
        y = np.asarray([sample_rows[index]["y"] for index in indices], dtype=np.int64)
        if len(set(y.tolist())) != 2:
            continue
        probabilities = np.asarray(
            [sample_rows[index]["probability"] for index in indices], dtype=np.float64
        )
        predicted = np.asarray(
            [sample_rows[index]["predicted"] for index in indices], dtype=np.bool_
        )
        observed = _metrics_from_arrays(y, probabilities, predicted)
        for name, value in observed.items():
            distributions[name].append(value)
    if len(distributions["roc_auc"]) != iterations:
        raise ValueError("Group bootstrap could not produce the requested valid resamples.")
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


def _diagnostic_curves(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    y = np.asarray([int(item["observed_positive"]) for item in predictions], dtype=np.int64)
    probabilities = np.asarray(
        [item["positive_probability"] for item in predictions], dtype=np.float64
    )
    false_positive_rate, true_positive_rate, roc_thresholds = roc_curve(y, probabilities)
    precision, recall, pr_thresholds = precision_recall_curve(y, probabilities)
    bins = np.linspace(0, 1, 11)
    calibration = []
    for left, right in pairwise(bins):
        mask = (probabilities >= left) & (
            probabilities <= right if right == 1 else probabilities < right
        )
        if np.any(mask):
            calibration.append(
                {
                    "predicted_probability": float(np.mean(probabilities[mask])),
                    "observed_fraction": float(np.mean(y[mask])),
                    "sample_count": int(np.sum(mask)),
                }
            )
    clipped = np.clip(probabilities, 1e-6, 1 - 1e-6)
    log_odds = np.log(clipped / (1 - clipped)).reshape(-1, 1)
    calibration_fit = LogisticRegression(C=1_000_000, solver="lbfgs")
    calibration_fit.fit(log_odds, y)
    predicted = np.asarray([item["predicted_positive"] for item in predictions], dtype=np.bool_)
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    return {
        "roc_curve": [
            {
                "false_positive_rate": float(x),
                "true_positive_rate": float(y_value),
                "threshold": None if not np.isfinite(threshold) else float(threshold),
            }
            for x, y_value, threshold in zip(
                false_positive_rate, true_positive_rate, roc_thresholds, strict=True
            )
        ],
        "precision_recall_curve": [
            {
                "recall": float(recall[index]),
                "precision": float(precision[index]),
                "threshold": float(pr_thresholds[index]) if index < len(pr_thresholds) else None,
            }
            for index in range(len(precision))
        ],
        "calibration_curve": calibration,
        "calibration_intercept": float(calibration_fit.intercept_[0]),
        "calibration_slope": float(calibration_fit.coef_[0, 0]),
        "confusion_matrix": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
        },
    }


def _permuted_labels(
    y: NDArray[np.int64], groups: NDArray[np.str_] | None, rng: np.random.Generator
) -> NDArray[np.int64]:
    permuted = y.copy()
    if groups is None:
        return rng.permutation(permuted)
    group_ids = sorted(set(groups.tolist()))
    group_indices = [np.flatnonzero(groups == group) for group in group_ids]
    if all(len(set(y[indices].tolist())) == 1 for indices in group_indices):
        shuffled_labels = rng.permutation([int(y[indices[0]]) for indices in group_indices])
        for indices, label in zip(group_indices, shuffled_labels, strict=True):
            permuted[indices] = label
        return permuted
    for indices in group_indices:
        permuted[indices] = rng.permutation(permuted[indices])
    return permuted


def _permutation_control(
    matrix: NDArray[np.float64],
    y: NDArray[np.int64],
    groups: NDArray[np.str_] | None,
    config: ClassifierConfig,
    feature_count: int,
    observed_auc: float,
    *,
    workers: int = 1,
) -> dict[str, Any]:
    if config.permutation_count == 0:
        return {
            "method": "full_nested_cross_validation_label_permutation",
            "count": 0,
            "roc_auc_values": [],
            "empirical_p_value": None,
        }
    if workers < 1:
        raise ValueError("Classifier permutation workers must be at least one.")
    worker_count = min(workers, config.permutation_count)
    print(
        f"Classifier permutation control: 0/{config.permutation_count} complete "
        f"using {worker_count} worker(s).",
        file=sys.stderr,
        flush=True,
    )
    if worker_count == 1:
        completed = (
            _permutation_auc(permutation, matrix, y, groups, config, feature_count)
            for permutation in range(config.permutation_count)
        )
        indexed_values = _collect_permutation_values(completed, config.permutation_count)
    else:
        with parallel_config(backend="loky", inner_max_num_threads=1):
            completed = Parallel(
                n_jobs=worker_count,
                batch_size=1,
                max_nbytes="1M",
                mmap_mode="r",
                pre_dispatch=worker_count,
                return_as="generator_unordered",
            )(
                delayed(_permutation_auc)(
                    permutation, matrix, y, groups, config, feature_count
                )
                for permutation in range(config.permutation_count)
            )
            indexed_values = _collect_permutation_values(
                completed, config.permutation_count
            )
    values = [indexed_values[index] for index in range(config.permutation_count)]
    return {
        "method": "full_nested_cross_validation_label_permutation",
        "count": config.permutation_count,
        "roc_auc_values": values,
        "mean_roc_auc": float(np.mean(values)),
        "empirical_p_value": (1 + sum(value >= observed_auc for value in values))
        / (config.permutation_count + 1),
        "note": "Permutation respects the experimental-unit exchangeability structure: labels "
        "are shuffled between homogeneous units or within repeated-condition units. Feature "
        "selection, preprocessing, hyperparameter tuning, calibration, and fitting are repeated "
        "inside each permitted training scope. Seeds are derived from the frozen random seed and "
        "permutation index; result order is permutation-index order regardless of worker count.",
    }


def _collect_permutation_values(
    completed: Iterable[tuple[int, float]], total: int
) -> dict[int, float]:
    indexed_values: dict[int, float] = {}
    for completed_count, (permutation, value) in enumerate(completed, 1):
        indexed_values[permutation] = value
        print(
            f"Classifier permutation control: {completed_count}/{total} complete.",
            file=sys.stderr,
            flush=True,
        )
    return indexed_values


def _permutation_auc(
    permutation: int,
    matrix: NDArray[np.float64],
    y: NDArray[np.int64],
    groups: NDArray[np.str_] | None,
    config: ClassifierConfig,
    feature_count: int,
) -> tuple[int, float]:
    rng = np.random.default_rng(config.random_seed + 80_000 + permutation)
    permuted = _permuted_labels(y, groups, rng)
    probabilities = np.zeros(len(y) * config.repeats, dtype=np.float64)
    observed = np.zeros(len(y) * config.repeats, dtype=np.int64)
    cursor = 0
    for repeat in range(config.repeats):
        splits = _split(y, groups, config.outer_folds, config.random_seed + repeat)
        for fold_index, (training, test) in enumerate(splits):
            inner_seed = (
                config.random_seed
                + 90_000
                + permutation * 10_000
                + repeat * config.outer_folds
                + fold_index
            )
            inner_splits = _split(
                permuted[training],
                groups[training] if groups is not None else None,
                config.inner_folds,
                inner_seed,
            )
            best, inner_decisions = _tune(
                matrix[training],
                permuted[training],
                groups[training] if groups is not None else None,
                inner_splits,
                feature_count,
                config,
                inner_seed,
            )
            calibrator = _fit_calibrator(inner_decisions, permuted[training], config)
            fitted = _fit_fold_model(
                matrix[training],
                permuted[training],
                feature_count,
                best[0],
                best[1],
                config,
                inner_seed + 5_000,
            )
            count = len(test)
            probabilities[cursor : cursor + count] = _calibrate(
                fitted.decision_function(matrix[test]), calibrator
            )
            observed[cursor : cursor + count] = permuted[test]
            cursor += count
    return permutation, float(roc_auc_score(observed, probabilities))


def _learning_curve(
    matrix: NDArray[np.float64],
    y: NDArray[np.int64],
    groups: NDArray[np.str_] | None,
    folds: list[dict[str, Any]],
    config: ClassifierConfig,
    feature_count: int,
) -> list[dict[str, Any]]:
    results = []
    for fraction in (0.5, 0.75, 1.0):
        fold_scores = []
        for repeat in range(config.repeats):
            splits = _split(y, groups, config.outer_folds, config.random_seed + repeat)
            for fold_index, (training, test) in enumerate(splits):
                rng = np.random.default_rng(
                    config.random_seed + 100_000 + repeat * 100 + fold_index
                )
                if groups is None:
                    selected = rng.choice(
                        training, size=max(4, round(len(training) * fraction)), replace=False
                    )
                else:
                    train_groups = np.asarray(sorted(set(groups[training].tolist())))
                    rng.shuffle(train_groups)
                    keep = set(train_groups[: max(2, round(len(train_groups) * fraction))].tolist())
                    selected = np.asarray(
                        [index for index in training if groups[index] in keep], dtype=np.int64
                    )
                if len(set(y[selected].tolist())) != 2:
                    selected = training
                record = folds[repeat * config.outer_folds + fold_index]
                fitted = _fit_fold_model(
                    matrix[selected],
                    y[selected],
                    feature_count,
                    float(record["best_c"]),
                    float(record["best_l1_ratio"]),
                    config,
                    config.random_seed + 110_000 + repeat * 100 + fold_index,
                )
                fold_scores.append(
                    float(roc_auc_score(y[test], _sigmoid(fitted.decision_function(matrix[test]))))
                )
        results.append(
            {
                "training_fraction": fraction,
                "mean_roc_auc": float(np.mean(fold_scores)),
                "fold_roc_auc": fold_scores,
            }
        )
    return results


def _comparison_models(
    matrix: NDArray[np.float64],
    y: NDArray[np.int64],
    groups: NDArray[np.str_] | None,
    config: ClassifierConfig,
    feature_count: int,
    elastic_net_metrics: dict[str, float | int],
) -> list[dict[str, Any]]:
    """Evaluate fixed algorithm families on the same leakage-safe outer splits."""
    results: list[dict[str, Any]] = [
        {
            "method": "elastic_net",
            "role": "primary_locked_model",
            "metrics": {
                name: elastic_net_metrics[name]
                for name in ("roc_auc", "pr_auc", "balanced_accuracy", "brier_score")
            },
            "tuning_scope": "inner_training_folds_only",
        }
    ]
    algorithms: dict[str, tuple[dict[str, Any], ...]] = {
        "random_forest": (
            {"max_depth": None, "min_samples_leaf": 1},
            {"max_depth": 5, "min_samples_leaf": 3},
        ),
        "hist_gradient_boosting": (
            {"max_leaf_nodes": 7, "l2_regularization": 0.0},
            {"max_leaf_nodes": 15, "l2_regularization": 1.0},
        ),
    }
    for algorithm, candidates in algorithms.items():
        probabilities: list[float] = []
        observed: list[int] = []
        best_parameters: list[dict[str, Any]] = []
        for repeat in range(config.repeats):
            splits = _split(y, groups, config.outer_folds, config.random_seed + repeat)
            for fold_index, (training, test) in enumerate(splits):
                inner_seed = config.random_seed + 140_000 + repeat * 100 + fold_index
                inner_splits = _split(
                    y[training],
                    groups[training] if groups is not None else None,
                    config.inner_folds,
                    inner_seed,
                )
                best = _tune_tree_model(
                    algorithm,
                    candidates,
                    matrix[training],
                    y[training],
                    inner_splits,
                    config,
                    feature_count,
                    inner_seed,
                )
                train_matrix, test_matrix = _variance_selected_matrices(
                    matrix[training], matrix[test], feature_count
                )
                estimator = _tree_estimator(algorithm, best, config, inner_seed + 5_000)
                estimator.fit(train_matrix, y[training])
                probabilities.extend(
                    cast(NDArray[np.float64], estimator.predict_proba(test_matrix)[:, 1]).tolist()
                )
                observed.extend(y[test].tolist())
                best_parameters.append({"repeat": repeat + 1, "fold": fold_index + 1, **best})
        y_oof = np.asarray(observed, dtype=np.int64)
        probability_array = np.asarray(probabilities, dtype=np.float64)
        results.append(
            {
                "method": algorithm,
                "role": "comparison_only_not_exported",
                "metrics": _metrics_from_arrays(y_oof, probability_array, probability_array >= 0.5),
                "tuning_scope": "inner_training_folds_only",
                "best_parameters_by_outer_fold": best_parameters,
            }
        )
    return results


def _tune_tree_model(
    algorithm: str,
    candidates: tuple[dict[str, Any], ...],
    matrix: NDArray[np.float64],
    y: NDArray[np.int64],
    splits: list[tuple[NDArray[np.int64], NDArray[np.int64]]],
    config: ClassifierConfig,
    feature_count: int,
    seed: int,
) -> dict[str, Any]:
    best = candidates[0]
    best_score = -np.inf
    for candidate_index, candidate in enumerate(candidates):
        probabilities = np.full(len(y), np.nan, dtype=np.float64)
        for fold_index, (training, validation) in enumerate(splits):
            train_matrix, validation_matrix = _variance_selected_matrices(
                matrix[training], matrix[validation], feature_count
            )
            estimator = _tree_estimator(
                algorithm, candidate, config, seed + candidate_index * 100 + fold_index
            )
            estimator.fit(train_matrix, y[training])
            probabilities[validation] = estimator.predict_proba(validation_matrix)[:, 1]
        score = _primary_score(y, probabilities, config.primary_metric)
        if score > best_score + 1e-12:
            best_score, best = score, candidate
    return dict(best)


def _variance_selected_matrices(
    training: NDArray[np.float64], evaluation: NDArray[np.float64], feature_count: int
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    variances = np.var(training, axis=0, ddof=1)
    selected = np.lexsort((np.arange(training.shape[1]), -variances))[:feature_count]
    return training[:, selected], evaluation[:, selected]


def _tree_estimator(
    algorithm: str, parameters: dict[str, Any], config: ClassifierConfig, seed: int
) -> RandomForestClassifier | HistGradientBoostingClassifier:
    class_weight = "balanced" if config.class_weight == "balanced" else None
    if algorithm == "random_forest":
        return RandomForestClassifier(
            n_estimators=100,
            max_depth=parameters["max_depth"],
            min_samples_leaf=int(parameters["min_samples_leaf"]),
            class_weight=class_weight,
            n_jobs=1,
            random_state=seed,
        )
    return HistGradientBoostingClassifier(
        max_iter=100,
        max_leaf_nodes=int(parameters["max_leaf_nodes"]),
        min_samples_leaf=5,
        l2_regularization=float(parameters["l2_regularization"]),
        class_weight=class_weight,
        early_stopping=False,
        random_state=seed,
    )


def _metadata_values(
    sample_ids: list[str],
    metadata: dict[str, dict[str, str]],
    column: str | None,
) -> list[str]:
    if column is None:
        return []
    try:
        values = [metadata[sample_id][column].strip() for sample_id in sample_ids]
    except KeyError as error:
        raise ValueError(f"Classifier metadata column '{column}' is missing.") from error
    if any(not value for value in values):
        raise ValueError(f"Classifier metadata column '{column}' contains missing values.")
    return values


def _class_counts(y: NDArray[np.int64], negative: str, positive: str) -> dict[str, int]:
    counts = Counter(y.tolist())
    return {negative: counts[0], positive: counts[1]}


def _assert_disjoint_scope(
    training: NDArray[np.int64], test: NDArray[np.int64], label: str
) -> None:
    if set(training.tolist()) & set(test.tolist()):
        raise ValueError(f"Leakage trap detected: {label} fit scope includes evaluation samples.")


def validate_leakage_audit(folds: list[dict[str, Any]]) -> None:
    """Reject audit records produced by an intentionally leaky implementation."""
    for fold in folds:
        fit_ids = set(cast(list[str], fold["preprocessing_fit_sample_ids"]))
        test_ids = set(cast(list[str], fold["outer_test_sample_ids"]))
        if fit_ids & test_ids:
            raise ValueError("Leakage trap detected: preprocessing observed an outer test sample.")


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
    expected = [{field: item[field] for field in fields} for item in frozen]
    observed = [{field: item[field] for field in fields} for item in folds]
    if observed != expected:
        raise ValueError("Scientific runner split plan differs from the frozen server audit.")


def _validate_oof_coverage(
    predictions: list[dict[str, Any]], sample_ids: list[str], repeats: int
) -> None:
    counts = Counter((item["sample_id"], item["repeat"]) for item in predictions)
    expected = {(sample_id, repeat) for sample_id in sample_ids for repeat in range(1, repeats + 1)}
    if set(counts) != expected or any(value != 1 for value in counts.values()):
        raise ValueError("OOF coverage must contain exactly one prediction per sample per repeat.")


def _digest_ids(values: list[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(values)) + "\n").encode()).hexdigest()


def _fit_locked_model(
    matrix: NDArray[np.float64],
    y: NDArray[np.int64],
    groups: NDArray[np.str_] | None,
    feature_ids: list[str],
    negative_class: str,
    config: ClassifierConfig,
    feature_count: int,
) -> dict[str, Any]:
    tuning_splits = _split(y, groups, config.inner_folds, config.random_seed + 120_000)
    best, decisions = _tune(
        matrix, y, groups, tuning_splits, feature_count, config, config.random_seed + 120_000
    )
    calibrator = _fit_calibrator(decisions, y, config)
    probabilities = _calibrate(decisions, calibrator)
    threshold = (
        _youden_threshold(y, probabilities)
        if config.decision_threshold_strategy == "inner_cv_youden"
        else 0.5
    )
    fitted = _fit_fold_model(
        matrix, y, feature_count, best[0], best[1], config, config.random_seed + 130_000
    )
    selected_ids = [feature_ids[index] for index in fitted.feature_indices]
    return {
        "schema_version": "1.0.0",
        "model_type": "binary_elastic_net_logistic_regression",
        "analysis_id": config.analysis_id,
        "prepared_dataset_id": config.prepared_dataset_id,
        "assay": config.assay,
        "outcome_column": config.outcome_column,
        "negative_class": negative_class,
        "positive_class": config.positive_class,
        "selected_feature_ids": selected_ids,
        "preprocessing": {
            "feature_filter": "top_variance_fit_on_complete_development_cohort_after_validation",
            "means": fitted.means.tolist(),
            "scales": fitted.scales.tolist(),
        },
        "estimator": {
            "c": best[0],
            "l1_ratio": best[1],
            "coefficients": cast(NDArray[np.float64], fitted.model.coef_[0]).tolist(),
            "intercept": float(fitted.model.intercept_[0]),
        },
        "calibration": {
            "method": config.probability_calibration,
            "coefficient": float(calibrator.coef_[0, 0]) if calibrator is not None else None,
            "intercept": float(calibrator.intercept_[0]) if calibrator is not None else None,
        },
        "decision_threshold": threshold,
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
        "title": "TranscriptForge locked classifier inference input",
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


def _model_card(result: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "model_name": "TranscriptForge binary elastic-net research classifier",
        "intended_use": (
            "Research-only hypothesis generation on compatible human gene-level log-expression "
            "data."
        ),
        "prohibited_use": (
            "Clinical diagnosis, treatment selection, prognosis, or deployment without "
            "independent validation and review."
        ),
        "development_data": {
            "prepared_dataset_id": result["prepared_dataset_id"],
            "sample_count": result["sample_count"],
            "outcome": result["outcome"],
            "group_column": result["validation"]["group_column"],
            "cohort_column": result["validation"]["cohort_column"],
        },
        "validation": {
            "type": "internal_grouped_repeated_nested_cross_validation",
            "metrics": result["metrics"],
            "confidence_intervals": result["confidence_intervals"],
            "permutation_control": result["permutation_control"],
            "external_validation_completed": False,
        },
        "model": {
            "type": model["model_type"],
            "selected_feature_count": len(model["selected_feature_ids"]),
            "decision_threshold": model["decision_threshold"],
            "calibration": model["calibration"]["method"],
        },
        "limitations": [
            "Internal OOF performance is not external validation.",
            "Feature stability and performance may change across cohorts, platforms, and "
            "preprocessing.",
            "Missing required features or incompatible assay scale must block inference.",
        ],
    }


def _model_card_markdown(card: dict[str, Any]) -> str:
    metrics = card["validation"]["metrics"]
    return (
        "# TranscriptForge binary elastic-net research classifier\n\n"
        "## Intended research use\n\n" + str(card["intended_use"]) + "\n\n"
        "## Prohibited use\n\n" + str(card["prohibited_use"]) + "\n\n"
        "## Internal validation\n\n"
        f"- ROC-AUC: {float(metrics['roc_auc']):.3f}\n"
        f"- PR-AUC: {float(metrics['pr_auc']):.3f}\n"
        f"- Balanced accuracy: {float(metrics['balanced_accuracy']):.3f}\n\n"
        "## Limitations\n\n" + "\n".join(f"- {item}" for item in card["limitations"]) + "\n"
    )


def _write_inference_example(path: Path, model: dict[str, Any]) -> None:
    selected = cast(list[str], model["selected_feature_ids"])
    # The example demonstrates shape and identifiers; values are intentionally blank to prevent
    # a development sample from being mistaken for independent prediction evidence.
    path.write_text(
        "sample_id\t"
        + "\t".join(selected)
        + "\nexample_sample\t"
        + "\t".join("" for _ in selected)
        + "\n",
        encoding="utf-8",
    )


def _write_diagnostic_svg(
    path: Path, diagnostics: dict[str, Any], learning_curve: list[dict[str, Any]]
) -> None:
    roc_points = " ".join(
        f"{40 + 240 * float(item['false_positive_rate']):.1f},"
        f"{280 - 240 * float(item['true_positive_rate']):.1f}"
        for item in diagnostics["roc_curve"]
    )
    pr_points = " ".join(
        f"{340 + 240 * float(item['recall']):.1f},{280 - 240 * float(item['precision']):.1f}"
        for item in diagnostics["precision_recall_curve"]
    )
    learning_points = " ".join(
        f"{690 + 220 * float(item['training_fraction']):.1f},"
        f"{280 - 240 * float(item['mean_roc_auc']):.1f}"
        for item in learning_curve
    )
    path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' width='960' height='330' viewBox='0 0 960 330'>"
        "<rect width='960' height='330' fill='white'/><g font-family='system-ui' fill='#17323a'>"
        "<text x='40' y='24' font-weight='700'>ROC curve</text>"
        "<text x='340' y='24' font-weight='700'>Precision-recall</text>"
        "<text x='660' y='24' font-weight='700'>Learning curve</text></g>"
        "<g fill='none' stroke='#ccd' stroke-width='1'>"
        "<path d='M40 40V280H280'/><path d='M340 40V280H580'/>"
        "<path d='M660 40V280H920'/></g>"
        f"<polyline points='{roc_points}' fill='none' stroke='#7c3aed' stroke-width='3'/>"
        f"<polyline points='{pr_points}' fill='none' stroke='#155e75' stroke-width='3'/>"
        f"<polyline points='{learning_points}' fill='none' stroke='#d97706' stroke-width='3'/>"
        "</svg>\n",
        encoding="utf-8",
    )


def _write_predictions(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _write_features(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        fields = ["feature_id", "selection_frequency", "nonzero_frequency", "mean_coefficient"]
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _result_manifest(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "analysis_type": "classifier",
        "title": "Binary elastic-net classifier",
        "summary_metrics": [
            {"label": "Samples", "value": result["sample_count"]},
            {"label": "ROC-AUC", "value": result["metrics"]["roc_auc"]},
            {"label": "PR-AUC", "value": result["metrics"]["pr_auc"]},
            {"label": "Balanced accuracy", "value": result["metrics"]["balanced_accuracy"]},
            {
                "label": "Calibration slope",
                "value": result["diagnostic_curves"]["calibration_slope"],
            },
            {
                "label": "Permutation p-value",
                "value": result["permutation_control"]["empirical_p_value"],
            },
        ],
        "sections": [
            {
                "id": "validation",
                "title": "Internal validation",
                "items": [
                    {
                        "type": "image",
                        "title": "Classifier diagnostics",
                        "path": "classifier_diagnostics.svg",
                    },
                    {
                        "type": "file",
                        "title": "Classifier diagnostics data",
                        "path": "classifier_diagnostics.json",
                    },
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
                    {
                        "type": "file",
                        "title": "Inference schema",
                        "path": "inference_schema.json",
                    },
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
            {
                "type": "image",
                "title": "Classifier diagnostics",
                "path": "classifier_diagnostics.svg",
            },
            {"type": "file", "title": "Locked model", "path": "model.json"},
            {"type": "file", "title": "Model card", "path": "model_card.json"},
            {"type": "file", "title": "Inference schema", "path": "inference_schema.json"},
            {"type": "table", "title": "Inference example", "path": "inference_example.tsv"},
            {"type": "html", "title": "Classifier report", "path": "report.html"},
            {"type": "file", "title": "Quarto report source", "path": "report.qmd"},
        ],
        "warnings": result["warnings"],
    }
