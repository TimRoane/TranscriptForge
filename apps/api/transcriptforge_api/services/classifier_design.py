"""Leakage-resistant binary and multiclass classifier design validation."""

from __future__ import annotations

from collections import Counter

import numpy as np
from numpy.typing import NDArray
from sklearn.model_selection import (  # type: ignore[import-untyped]
    StratifiedGroupKFold,
    StratifiedKFold,
)

from transcriptforge_api.models import PreparedDataset
from transcriptforge_api.schemas.analyses import (
    ClassifierDesignValidationRead,
    ClassifierFoldRead,
    ClassifierPreviewRequest,
)
from transcriptforge_api.services.design_validation import design_options
from transcriptforge_api.storage.base import StorageBackend

_MISSING = {"", "na", "nan", "null", "none"}
_EXPERIMENTAL_UNIT_NAMES = {
    "donor",
    "donor_id",
    "subject",
    "subject_id",
    "patient",
    "patient_id",
    "participant",
    "participant_id",
    "individual",
    "individual_id",
}


def validate_classifier_design(
    prepared: PreparedDataset,
    storage: StorageBackend,
    request: ClassifierPreviewRequest,
) -> ClassifierDesignValidationRead:
    """Build and audit a repeated nested-CV split plan without fitting a model."""
    rows, options = design_options(prepared, storage)
    parameters = request.parameters
    binary = request.method == "elastic_net"
    errors: list[str] = []
    warnings: list[str] = []
    known = {item.name: item for item in options.variables}
    if request.assay not in prepared.value_types_available:
        errors.append("The log_expression assay is not available in this Expression Bundle.")
    if parameters.top_variable_features > prepared.feature_count:
        errors.append(
            f"Top-variable feature count ({parameters.top_variable_features}) exceeds the "
            f"bundle feature count ({prepared.feature_count})."
        )
    outcome = known.get(parameters.outcome_column)
    outcome_values = [row.get(parameters.outcome_column, "").strip() for row in rows]
    if outcome is None:
        errors.append(f"Outcome column '{parameters.outcome_column}' is not present in metadata.")
        levels: list[str] = []
    elif any(value.casefold() in _MISSING for value in outcome_values):
        errors.append(f"Outcome column '{parameters.outcome_column}' contains missing values.")
        levels = sorted({value for value in outcome_values if value.casefold() not in _MISSING})
    else:
        levels = sorted(set(outcome_values))
        valid_level_count = len(levels) == 2 if binary else 3 <= len(levels) <= 20
        if not valid_level_count:
            errors.append(
                (
                    "Binary classification requires exactly two outcome levels; "
                    if binary
                    else "Multiclass classification requires between 3 and 20 outcome levels; "
                )
                + f"'{parameters.outcome_column}' has {len(levels)}."
            )
    if binary and levels and parameters.positive_class not in levels:
        errors.append(
            f"Positive class '{parameters.positive_class}' is absent from "
            f"'{parameters.outcome_column}'."
        )
    if not binary and parameters.positive_class is not None:
        errors.append("Multiclass classification does not use a positive class.")
    if not binary and parameters.primary_metric not in {
        "macro_roc_auc",
        "macro_f1",
        "balanced_accuracy",
    }:
        errors.append(
            "Multiclass classification requires macro ROC-AUC, macro F1, or balanced accuracy."
        )
    if binary and parameters.primary_metric not in {
        "roc_auc",
        "pr_auc",
        "balanced_accuracy",
    }:
        errors.append("Binary classification requires ROC-AUC, PR-AUC, or balanced accuracy.")
    if not binary and (
        parameters.probability_calibration != "none"
        or parameters.decision_threshold_strategy != "fixed_0_5"
    ):
        errors.append("Multiclass v1 requires uncalibrated argmax probabilities.")
    negative_class = (
        next(
            (level for level in levels if level != parameters.positive_class),
            None,
        )
        if binary
        else None
    )
    class_counts = dict(Counter(outcome_values)) if outcome is not None else {}

    group_values: list[str] | None = None
    if parameters.group_column is not None:
        group = known.get(parameters.group_column)
        if group is None:
            errors.append(f"Group column '{parameters.group_column}' is not present in metadata.")
        else:
            group_values = [row.get(parameters.group_column, "").strip() for row in rows]
            if any(value.casefold() in _MISSING for value in group_values):
                errors.append(f"Group column '{parameters.group_column}' contains missing values.")
            if len(set(group_values)) < parameters.outer_folds:
                errors.append(
                    f"Group column '{parameters.group_column}' has {len(set(group_values))} "
                    f"groups; at least {parameters.outer_folds} are required for outer CV."
                )
    else:
        repeated_unit = next(
            (
                variable
                for variable in options.variables
                if _normalized_name(variable.name) in _EXPERIMENTAL_UNIT_NAMES
                and 1 < variable.unique_count < options.sample_count
                and variable.missing_count == 0
            ),
            None,
        )
        if repeated_unit is not None:
            errors.append(
                f"Repeated experimental-unit column '{repeated_unit.name}' was detected. Select "
                "it as the group column so related samples cannot cross folds."
            )
        else:
            warnings.append(
                "No repeated-sample group was selected; folds treat every sample as an independent "
                "experimental unit."
            )

    if parameters.cohort_column is not None:
        cohort = known.get(parameters.cohort_column)
        if cohort is None:
            errors.append(f"Cohort column '{parameters.cohort_column}' is not present in metadata.")
        else:
            cohort_values = [row.get(parameters.cohort_column, "").strip() for row in rows]
            if any(value.casefold() in _MISSING for value in cohort_values):
                errors.append(
                    f"Cohort column '{parameters.cohort_column}' contains missing values."
                )
            if cohort.unique_count < 2:
                warnings.append(
                    f"Cohort column '{parameters.cohort_column}' has only one observed value."
                )
    else:
        warnings.append("No cohort/site column was selected for stratified performance reporting.")

    expected_class_count = 2 if binary else len(levels)
    if expected_class_count >= 2 and len(levels) == expected_class_count:
        minority = min(class_counts[level] for level in levels)
        majority = max(class_counts[level] for level in levels)
        if group_values is None and minority < parameters.outer_folds:
            errors.append(
                f"The minority class has {minority} samples; at least {parameters.outer_folds} "
                "are required for stratified outer CV."
            )
        if group_values is not None:
            class_group_counts = {
                level: len(
                    {
                        group_values[index]
                        for index, value in enumerate(outcome_values)
                        if value == level
                    }
                )
                for level in levels
            }
            insufficient = {
                level: count
                for level, count in class_group_counts.items()
                if count < parameters.outer_folds
            }
            if insufficient:
                errors.append(
                    "Each outcome class must occur in at least the requested number of groups; "
                    + ", ".join(f"{level}: {count}" for level, count in insufficient.items())
                    + "."
                )
        if minority / majority < 0.25:
            warnings.append(
                "The outcome is severely imbalanced; retain class weighting and emphasize PR-AUC."
            )

    if len(rows) < 50:
        warnings.append(
            "Fewer than 50 samples are available; internal performance and feature stability may "
            "be highly uncertain."
        )
    warnings.append(
        "This design is internal validation only. It does not substitute for an untouched external "
        "cohort."
    )

    fold_plan: list[ClassifierFoldRead] = []
    if not errors and len(levels) == expected_class_count:
        fold_plan, split_errors = _build_fold_plan(
            outcome_values,
            group_values,
            outer_folds=parameters.outer_folds,
            inner_folds=parameters.inner_folds,
            repeats=parameters.repeats,
            random_seed=request.random_seed,
            expected_class_count=expected_class_count,
        )
        errors.extend(split_errors)
        if split_errors:
            fold_plan = []
    group_count = len(set(group_values)) if group_values is not None else len(rows)
    valid = not errors
    return ClassifierDesignValidationRead(
        valid=valid,
        method=request.method,
        assay=request.assay,
        outcome_column=parameters.outcome_column,
        negative_class=negative_class,
        positive_class=parameters.positive_class,
        class_labels=levels,
        eligible_sample_count=len(rows),
        class_counts=class_counts,
        group_column=parameters.group_column,
        group_count=group_count,
        cohort_column=parameters.cohort_column,
        outer_folds=parameters.outer_folds,
        inner_folds=parameters.inner_folds,
        repeats=parameters.repeats,
        expected_oof_prediction_count=len(rows) * parameters.repeats if valid else 0,
        preprocessing_scope="fit_inside_each_training_fold",
        tuning_scope="inner_training_folds_only",
        fold_plan=fold_plan,
        errors=errors,
        warnings=warnings,
    )


def _build_fold_plan(
    outcomes: list[str],
    groups: list[str] | None,
    *,
    outer_folds: int,
    inner_folds: int,
    repeats: int,
    random_seed: int,
    expected_class_count: int,
) -> tuple[list[ClassifierFoldRead], list[str]]:
    y = np.asarray(outcomes, dtype=np.str_)
    group_array = np.asarray(groups, dtype=np.str_) if groups is not None else None
    plan: list[ClassifierFoldRead] = []
    errors: list[str] = []
    for repeat_index in range(repeats):
        try:
            outer = _split(y, group_array, outer_folds, random_seed + repeat_index)
        except ValueError as error:
            return [], [f"Outer cross-validation is infeasible: {error}"]
        for fold_index, (training, test) in enumerate(outer, 1):
            training_classes = Counter(y[training].tolist())
            test_classes = Counter(y[test].tolist())
            if (
                len(training_classes) != expected_class_count
                or len(test_classes) != expected_class_count
            ):
                errors.append(
                    f"Repeat {repeat_index + 1}, outer fold {fold_index} does not contain all "
                    "classes in training and test partitions."
                )
                continue
            training_groups = (
                set(group_array[training].tolist())
                if group_array is not None
                else {str(index) for index in training.tolist()}
            )
            test_groups = (
                set(group_array[test].tolist())
                if group_array is not None
                else {str(index) for index in test.tolist()}
            )
            overlap = training_groups & test_groups
            if overlap:
                errors.append(
                    f"Repeat {repeat_index + 1}, outer fold {fold_index} leaks "
                    f"{len(overlap)} group(s) across training and test."
                )
                continue
            inner_groups = group_array[training] if group_array is not None else None
            try:
                inner = _split(
                    y[training],
                    inner_groups,
                    inner_folds,
                    random_seed + 10_000 + repeat_index * outer_folds + fold_index,
                )
            except ValueError as error:
                errors.append(
                    f"Repeat {repeat_index + 1}, outer fold {fold_index} cannot support "
                    f"{inner_folds}-fold inner tuning: {error}"
                )
                continue
            if any(
                len(set(y[training][inner_train].tolist())) != expected_class_count
                or len(set(y[training][inner_test].tolist())) != expected_class_count
                for inner_train, inner_test in inner
            ):
                errors.append(
                    f"Repeat {repeat_index + 1}, outer fold {fold_index} has an inner fold without "
                    f"all {expected_class_count} outcome classes."
                )
                continue
            plan.append(
                ClassifierFoldRead(
                    repeat=repeat_index + 1,
                    fold=fold_index,
                    training_sample_count=len(training),
                    test_sample_count=len(test),
                    training_class_counts=dict(training_classes),
                    test_class_counts=dict(test_classes),
                    training_group_count=len(training_groups),
                    test_group_count=len(test_groups),
                    group_overlap_count=0,
                )
            )
    return plan, errors


def _split(
    y: NDArray[np.str_],
    groups: NDArray[np.str_] | None,
    folds: int,
    random_seed: int,
) -> list[tuple[NDArray[np.int64], NDArray[np.int64]]]:
    placeholder = np.zeros((len(y), 1), dtype=np.float64)
    if groups is None:
        splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_seed)
        return [(training, test) for training, test in splitter.split(placeholder, y)]
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=random_seed)
    return [(training, test) for training, test in splitter.split(placeholder, y, groups)]


def _normalized_name(value: str) -> str:
    return value.strip().casefold().replace("-", "_").replace(" ", "_")
