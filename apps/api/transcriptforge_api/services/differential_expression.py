"""Read-only exploration helpers for differential-expression run artifacts."""

import csv
import io
import math
from collections import defaultdict
from statistics import mean, median
from typing import Any

from transcriptforge_api.schemas.runs import (
    DifferentialExpressionFeatureDetail,
    DifferentialExpressionResultRow,
    DifferentialExpressionResultsPage,
    DifferentialExpressionSort,
    ExpressionGroupSummary,
    ExpressionValue,
    FeatureExpressionProfile,
    SortDirection,
)


class DifferentialExpressionArtifactError(ValueError):
    """Raised when a published result artifact is malformed or inconsistent."""


def parse_results(payload: bytes) -> tuple[list[DifferentialExpressionResultRow], str]:
    """Parse the method-specific result table into one stable API shape."""
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8")), delimiter="\t")
    fieldnames = set(reader.fieldnames or ())
    required = {
        "feature_id",
        "log2_fold_change",
        "standard_error",
        "statistic",
        "p_value",
        "adjusted_p_value",
        "significant",
    }
    missing = sorted(required - fieldnames)
    if missing:
        raise DifferentialExpressionArtifactError(
            "Differential-expression results are missing columns: " + ", ".join(missing)
        )
    abundance_labels = {
        "base_mean": "Base mean normalized count",
        "average_log_cpm": "Average log2 CPM",
        "average_expression": "Average log2 expression",
    }
    abundance_column = next(
        (column for column in abundance_labels if column in fieldnames), None
    )
    if abundance_column is None:
        raise DifferentialExpressionArtifactError(
            "Differential-expression results do not contain an abundance column."
        )
    label = abundance_labels[abundance_column]
    rows = [
        DifferentialExpressionResultRow(
            feature_id=str(row["feature_id"]),
            gene_symbol=_optional_text(row.get("gene_symbol")),
            base_expression=_optional_float(row.get(abundance_column)),
            log2_fold_change=_optional_float(row.get("log2_fold_change")),
            standard_error=_optional_float(row.get("standard_error")),
            statistic=_optional_float(row.get("statistic")),
            p_value=_optional_float(row.get("p_value")),
            adjusted_p_value=_optional_float(row.get("adjusted_p_value")),
            significant=str(row.get("significant", "")).strip().lower() == "true",
            contrast=_optional_text(row.get("contrast")),
            method=_optional_text(row.get("method")),
        )
        for row in reader
    ]
    return rows, label


def result_page(
    payload: bytes,
    *,
    search: str | None,
    fdr_max: float | None,
    absolute_log2_fold_change_min: float | None,
    significant_only: bool,
    sort_by: DifferentialExpressionSort,
    direction: SortDirection,
    offset: int,
    limit: int,
) -> DifferentialExpressionResultsPage:
    rows, label = parse_results(payload)
    filtered = filter_results(
        rows,
        search=search,
        fdr_max=fdr_max,
        absolute_log2_fold_change_min=absolute_log2_fold_change_min,
        significant_only=significant_only,
    )
    ordered = sort_results(filtered, sort_by=sort_by, direction=direction)
    return DifferentialExpressionResultsPage(
        items=ordered[offset : offset + limit],
        total=len(ordered),
        offset=offset,
        limit=limit,
        base_expression_label=label,
    )


def filter_results(
    rows: list[DifferentialExpressionResultRow],
    *,
    search: str | None,
    fdr_max: float | None,
    absolute_log2_fold_change_min: float | None,
    significant_only: bool,
) -> list[DifferentialExpressionResultRow]:
    query = (search or "").strip().casefold()
    result = []
    for row in rows:
        if query and query not in row.feature_id.casefold() and query not in (
            row.gene_symbol or ""
        ).casefold():
            continue
        if fdr_max is not None and (
            row.adjusted_p_value is None or row.adjusted_p_value > fdr_max
        ):
            continue
        if absolute_log2_fold_change_min is not None and (
            row.log2_fold_change is None
            or abs(row.log2_fold_change) < absolute_log2_fold_change_min
        ):
            continue
        if significant_only and not row.significant:
            continue
        result.append(row)
    return result


def sort_results(
    rows: list[DifferentialExpressionResultRow],
    *,
    sort_by: DifferentialExpressionSort,
    direction: SortDirection,
) -> list[DifferentialExpressionResultRow]:
    available = [row for row in rows if getattr(row, sort_by) is not None]
    unavailable = [row for row in rows if getattr(row, sort_by) is None]
    available.sort(
        key=lambda row: _sort_value(getattr(row, sort_by)),
        reverse=direction == "desc",
    )
    unavailable.sort(key=lambda row: row.feature_id)
    return [*available, *unavailable]


def filtered_tsv(
    payload: bytes,
    *,
    search: str | None,
    fdr_max: float | None,
    absolute_log2_fold_change_min: float | None,
    significant_only: bool,
    sort_by: DifferentialExpressionSort,
    direction: SortDirection,
) -> str:
    rows, label = parse_results(payload)
    rows = sort_results(
        filter_results(
            rows,
            search=search,
            fdr_max=fdr_max,
            absolute_log2_fold_change_min=absolute_log2_fold_change_min,
            significant_only=significant_only,
        ),
        sort_by=sort_by,
        direction=direction,
    )
    destination = io.StringIO(newline="")
    writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
    writer.writerow(
        [
            "feature_id",
            "gene_symbol",
            label,
            "log2_fold_change",
            "standard_error",
            "statistic",
            "p_value",
            "adjusted_p_value",
            "significant",
            "contrast",
            "method",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.feature_id,
                row.gene_symbol or "",
                _format_optional(row.base_expression),
                _format_optional(row.log2_fold_change),
                _format_optional(row.standard_error),
                _format_optional(row.statistic),
                _format_optional(row.p_value),
                _format_optional(row.adjusted_p_value),
                str(row.significant).lower(),
                row.contrast or "",
                row.method or "",
            ]
        )
    return destination.getvalue()


def feature_detail(
    result_payload: bytes,
    feature_id: str,
    *,
    expression_payload: bytes | None,
    heatmap_contract: dict[str, Any] | None,
) -> DifferentialExpressionFeatureDetail | None:
    rows, label = parse_results(result_payload)
    result = next((row for row in rows if row.feature_id == feature_id), None)
    if result is None:
        return None
    profile = None
    if expression_payload is not None and heatmap_contract is not None:
        profile = _expression_profile(expression_payload, heatmap_contract, feature_id)
    return DifferentialExpressionFeatureDetail(
        result=result,
        base_expression_label=label,
        expression_profile=profile,
    )


def _expression_profile(
    payload: bytes, contract: dict[str, Any], feature_id: str
) -> FeatureExpressionProfile:
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8")), delimiter="\t")
    sample_ids = [value for value in (reader.fieldnames or []) if value != "feature_id"]
    row = next((item for item in reader if item.get("feature_id") == feature_id), None)
    if row is None:
        raise DifferentialExpressionArtifactError(
            f"Normalized expression is missing feature '{feature_id}'."
        )
    metadata = contract.get("metadata", {})
    contrast = contract.get("contrast", {})
    variable = str(contrast.get("variable", ""))
    values = [
        ExpressionValue(
            sample_id=sample_id,
            value=_required_float(row.get(sample_id), f"expression value for {sample_id}"),
            metadata={str(key): str(value) for key, value in metadata.get(sample_id, {}).items()},
        )
        for sample_id in sample_ids
    ]
    grouped: dict[str, list[float]] = defaultdict(list)
    for item in values:
        grouped[item.metadata.get(variable, "Unavailable")].append(item.value)
    preferred_levels = [
        str(contrast.get("denominator", "")),
        str(contrast.get("numerator", "")),
    ]
    levels = [level for level in preferred_levels if level in grouped]
    levels.extend(sorted(level for level in grouped if level not in levels))
    summaries = [
        ExpressionGroupSummary(
            level=level,
            sample_count=len(grouped[level]),
            mean=mean(grouped[level]),
            median=median(grouped[level]),
            minimum=min(grouped[level]),
            maximum=max(grouped[level]),
        )
        for level in levels
    ]
    source = str(contract.get("source", "normalized expression"))
    return FeatureExpressionProfile(
        assay=str(contract.get("assay", "")),
        source=source,
        value_label=source,
        contrast={str(key): str(value) for key, value in contrast.items()},
        values=values,
        group_summaries=summaries,
    )


def _optional_text(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _optional_float(value: str | None) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    number = float(text)
    if not math.isfinite(number):
        return None
    return number


def _required_float(value: str | None, label: str) -> float:
    parsed = _optional_float(value)
    if parsed is None:
        raise DifferentialExpressionArtifactError(f"Invalid {label}.")
    return parsed


def _sort_value(value: object) -> float | str:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (float, int)):
        return float(value)
    return str(value).casefold()


def _format_optional(value: float | None) -> str:
    return "" if value is None else format(value, ".12g")
