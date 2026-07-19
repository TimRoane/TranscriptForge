"""Deterministic design checks for post-lock precision studies."""

from collections import Counter
from typing import Any

import numpy as np

from transcriptforge_api.schemas.studies import StudyAssignment


def validate_precision_design(
    assignments: list[StudyAssignment], factors: list[str]
) -> dict[str, Any]:
    included = [item for item in assignments if item.include]
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    measurement_ids = [item.measurement_id for item in assignments]
    if len(measurement_ids) != len(set(measurement_ids)):
        errors.append(
            {
                "code": "STUDY.MEASUREMENT_NOT_UNIQUE",
                "message": "Measurement identifiers must be unique.",
            }
        )
    sample_counts = Counter(item.biological_sample_id for item in included)
    if len(sample_counts) < 2:
        errors.append(
            {
                "code": "STUDY.BIOLOGICAL_SAMPLES_INSUFFICIENT",
                "message": "At least two biological samples are required.",
            }
        )
    under_repeated = sorted(sample for sample, count in sample_counts.items() if count < 2)
    if under_repeated:
        errors.append(
            {
                "code": "STUDY.REPEATS_INSUFFICIENT",
                "message": "Every biological sample requires at least two included measurements.",
                "facts": {"samples": under_repeated},
            }
        )
    factor_levels: dict[str, list[str]] = {}
    for factor in factors:
        levels = sorted({str(getattr(item, factor, None) or "") for item in included})
        factor_levels[factor] = levels
        if len(levels) < 2:
            errors.append(
                {
                    "code": "STUDY.FACTOR_LEVELS_INSUFFICIENT",
                    "message": f"Factor '{factor}' requires at least two observed levels.",
                }
            )
    columns = [np.ones(len(included))]
    for factor in factors:
        values = [str(getattr(item, factor, None) or "") for item in included]
        for level in factor_levels[factor][1:]:
            columns.append(np.asarray([1.0 if value == level else 0.0 for value in values]))
    matrix = np.column_stack(columns) if included else np.empty((0, 0))
    rank = int(np.linalg.matrix_rank(matrix)) if matrix.size else 0
    if matrix.shape[1] and rank < matrix.shape[1]:
        errors.append(
            {
                "code": "STUDY.FACTOR_CONFOUNDING",
                "message": (
                    "The declared precision factors are rank deficient or perfectly confounded."
                ),
                "facts": {"rank": rank, "columns": matrix.shape[1]},
            }
        )
    if len(included) < 12:
        warnings.append(
            {
                "code": "STUDY.SMALL_PRECISION_DESIGN",
                "message": "Fewer than 12 measurements may yield unstable variance estimates.",
            }
        )
    return {
        "schema_version": "1.0.0",
        "valid": not errors,
        "included_measurement_count": len(included),
        "biological_sample_count": len(sample_counts),
        "replicates_per_sample": dict(sorted(sample_counts.items())),
        "factor_levels": factor_levels,
        "design_matrix_rank": rank,
        "design_matrix_columns": int(matrix.shape[1]) if matrix.ndim == 2 else 0,
        "errors": errors,
        "warnings": warnings,
    }


def validate_input_degradation_limit_design(
    assignments: list[StudyAssignment], reference_level: float
) -> dict[str, Any]:
    """Validate ordered, paired post-lock input/quality limit measurements."""
    included = [item for item in assignments if item.include]
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    identifiers = [item.measurement_id for item in assignments]
    if len(identifiers) != len(set(identifiers)):
        errors.append(
            {
                "code": "STUDY.MEASUREMENT_NOT_UNIQUE",
                "message": "Measurement identifiers must be unique.",
            }
        )
    levels = sorted(
        {float(item.input_level) for item in included if item.input_level is not None},
        reverse=True,
    )
    if reference_level not in levels:
        errors.append(
            {
                "code": "STUDY.REFERENCE_LEVEL_MISSING",
                "message": "The declared reference input/quality level is absent.",
                "facts": {"reference_level": reference_level, "observed_levels": levels},
            }
        )
    if len(levels) < 3:
        errors.append(
            {
                "code": "STUDY.ORDERED_LEVELS_INSUFFICIENT",
                "message": (
                    "At least three ordered levels are required for trend and "
                    "consecutive-level rules."
                ),
            }
        )
    by_sample: dict[str, Counter[float]] = {}
    for item in included:
        if item.input_level is not None:
            by_sample.setdefault(item.biological_sample_id, Counter())[float(item.input_level)] += 1
    if len(by_sample) < 3:
        errors.append(
            {
                "code": "STUDY.BIOLOGICAL_SAMPLES_INSUFFICIENT",
                "message": "At least three biological samples are required.",
            }
        )
    incomplete = sorted(
        sample
        for sample, counts in by_sample.items()
        if any(counts[level] != 1 for level in levels)
    )
    if incomplete:
        errors.append(
            {
                "code": "STUDY.PAIRED_LEVELS_INCOMPLETE",
                "message": (
                    "Each biological sample must have exactly one measurement at every "
                    "ordered level."
                ),
                "facts": {"biological_sample_ids": incomplete},
            }
        )
    level_runs: dict[float, set[str]] = {}
    run_levels: dict[str, set[float]] = {}
    for item in included:
        if item.input_level is None or not item.run:
            continue
        level = float(item.input_level)
        level_runs.setdefault(level, set()).add(item.run)
        run_levels.setdefault(item.run, set()).add(level)
    confounded = (
        len(level_runs) > 1
        and all(len(values) == 1 for values in level_runs.values())
        and all(len(values) == 1 for values in run_levels.values())
    )
    if confounded:
        errors.append(
            {
                "code": "STUDY.INPUT_RUN_CONFOUNDED",
                "message": "Input/quality level is perfectly aligned with run.",
                "facts": {
                    "level_runs": {str(key): sorted(value) for key, value in level_runs.items()}
                },
            }
        )
    if any(item.quality_metric is None for item in included):
        warnings.append(
            {
                "code": "STUDY.QUALITY_METRIC_INCOMPLETE",
                "message": (
                    "Quality-interaction interpretation is limited because some quality "
                    "metrics are missing."
                ),
            }
        )
    return {
        "schema_version": "1.0.0",
        "valid": not errors,
        "included_measurement_count": len(included),
        "biological_sample_count": len(by_sample),
        "reference_level": reference_level,
        "ordered_levels": levels,
        "complete_pair_count": len(by_sample) - len(incomplete),
        "factor_levels": {"input_level": [str(value) for value in levels]},
        "design_matrix_rank": len(levels),
        "design_matrix_columns": len(levels),
        "errors": errors,
        "warnings": warnings,
    }


def validate_paired_bridging_design(
    assignments: list[StudyAssignment], reference: str, comparator: str
) -> dict[str, Any]:
    """Validate exact bridge pairs and reference/comparator identifiability."""
    included = [item for item in assignments if item.include]
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    identifiers = [item.measurement_id for item in assignments]
    if len(identifiers) != len(set(identifiers)):
        errors.append(
            {
                "code": "STUDY.MEASUREMENT_NOT_UNIQUE",
                "message": "Measurement identifiers must be unique.",
            }
        )
    observed = sorted({item.condition or "" for item in included if item.condition})
    if reference not in observed or comparator not in observed:
        errors.append(
            {
                "code": "STUDY.BRIDGE_CONDITION_MISSING",
                "message": "Both declared bridge conditions must be observed.",
                "facts": {"observed_conditions": observed},
            }
        )
    by_sample: dict[str, Counter[str]] = {}
    for item in included:
        if item.condition:
            by_sample.setdefault(item.biological_sample_id, Counter())[item.condition] += 1
    incomplete = sorted(
        sample
        for sample, counts in by_sample.items()
        if counts[reference] != 1 or counts[comparator] != 1
    )
    if incomplete:
        errors.append(
            {
                "code": "STUDY.BRIDGE_PAIRS_INCOMPLETE",
                "message": "Each biological sample requires exactly one reference and comparator.",
                "facts": {"biological_sample_ids": incomplete},
            }
        )
    if len(by_sample) < 4:
        errors.append(
            {
                "code": "STUDY.BRIDGE_PAIRS_INSUFFICIENT",
                "message": "At least four complete bridge pairs are required.",
            }
        )
    condition_runs: dict[str, set[str]] = {}
    run_conditions: dict[str, set[str]] = {}
    for item in included:
        if item.condition and item.run:
            condition_runs.setdefault(item.condition, set()).add(item.run)
            run_conditions.setdefault(item.run, set()).add(item.condition)
    confounded = (
        len(condition_runs) > 1
        and all(len(values) == 1 for values in condition_runs.values())
        and all(len(values) == 1 for values in run_conditions.values())
    )
    if confounded:
        errors.append(
            {
                "code": "STUDY.BRIDGE_CONDITION_RUN_CONFOUNDED",
                "message": "Bridge condition is perfectly aligned with run.",
            }
        )
    if not any(item.subgroup for item in included):
        warnings.append(
            {
                "code": "STUDY.BRIDGE_SUBGROUP_UNAVAILABLE",
                "message": "No subgroup field is available; subgroup review will be not estimable.",
            }
        )
    return {
        "schema_version": "1.0.0",
        "valid": not errors,
        "included_measurement_count": len(included),
        "biological_sample_count": len(by_sample),
        "reference_condition": reference,
        "comparator_condition": comparator,
        "complete_pair_count": len(by_sample) - len(incomplete),
        "factor_levels": {"condition": observed},
        "design_matrix_rank": 2 if included else 0,
        "design_matrix_columns": 2,
        "errors": errors,
        "warnings": warnings,
    }


def validate_robustness_interference_design(
    assignments: list[StudyAssignment], reference: str, challenge: str
) -> dict[str, Any]:
    """Validate exact challenge/reference pairs and challenge estimability."""
    result = validate_paired_bridging_design(assignments, reference, challenge)
    result["reference_condition"] = reference
    result["challenge_condition"] = challenge
    for finding in result["errors"]:
        finding["code"] = finding["code"].replace("BRIDGE", "CHALLENGE")
        finding["message"] = finding["message"].replace("Bridge", "Challenge/reference")
        finding["message"] = finding["message"].replace("bridge", "challenge/reference")
    for finding in result["warnings"]:
        finding["code"] = finding["code"].replace("BRIDGE", "CHALLENGE")
    included = [item for item in assignments if item.include]
    challenge_types = sorted(
        {item.challenge_type or "" for item in included if item.challenge_type}
    )
    if not challenge_types:
        result["errors"].append(
            {
                "code": "STUDY.CHALLENGE_TYPE_MISSING",
                "message": "At least one prespecified challenge type is required.",
            }
        )
    result["factor_levels"]["challenge_type"] = challenge_types
    result["valid"] = not result["errors"]
    return result
