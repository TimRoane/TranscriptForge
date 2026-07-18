"""Deterministic single-sample scoring of mapped gene signatures."""

from __future__ import annotations

import csv
import hashlib
import html
import json
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import scipy  # type: ignore[import-untyped]
from scipy.stats import f as f_distribution  # type: ignore[import-untyped]
from scipy.stats import pearsonr, rankdata
from scipy.stats import t as t_distribution

from transcriptforge_analysis.matrix_validation import write_json_atomic
from transcriptforge_analysis.pca import BundleAssay, load_bundle_assay
from transcriptforge_analysis.reporting import write_dimension_reduction_report

SignatureMethod = Literal["mean_expression", "mean_z_score", "weighted_linear", "rank_based"]
_CROSS_PLATFORM_WARNING = (
    "Raw signature scores must not be compared across RNA-seq, microarray, cohorts, or "
    "preprocessing pipelines; compare prespecified within-dataset direction, ranking, "
    "association, or standardized effects."
)


@dataclass(frozen=True, slots=True)
class SignatureScoringConfig:
    analysis_id: str
    prepared_dataset_id: str
    method: SignatureMethod
    assay: str
    mapping_id: str
    mapping_report_sha256: str
    mapping_report: dict[str, Any]
    phenotype_column: str | None = None
    phenotype_kind: Literal["auto", "categorical", "numeric"] = "auto"
    covariates: tuple[str, ...] = ()
    block_column: str | None = None

    @classmethod
    def from_json(cls, path: Path) -> SignatureScoringConfig:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("analysis_type") != "signature":
            raise ValueError("Signature scoring requires analysis_type 'signature'.")
        method = str(payload.get("method", ""))
        supported = {"mean_expression", "mean_z_score", "weighted_linear", "rank_based"}
        if method not in supported:
            raise ValueError(f"Unsupported signature-scoring method '{method}'.")
        assay = str(payload.get("assay", ""))
        if assay != "log_expression":
            raise ValueError("Signature scoring currently requires the log_expression assay.")
        mapping = payload.get("signature_mapping")
        if not isinstance(mapping, dict) or not isinstance(mapping.get("report"), dict):
            raise ValueError("The frozen signature mapping is missing.")
        association = payload.get("parameters", {}).get("phenotype_association", {})
        enabled = bool(association.get("enabled", False))
        phenotype_column = association.get("phenotype_column") if enabled else None
        if enabled and not phenotype_column:
            raise ValueError("Enabled phenotype association requires a phenotype column.")
        return cls(
            analysis_id=str(payload["analysis_id"]),
            prepared_dataset_id=str(payload["prepared_dataset_id"]),
            method=cast(SignatureMethod, method),
            assay=assay,
            mapping_id=str(mapping["id"]),
            mapping_report_sha256=str(mapping["report_sha256"]),
            mapping_report=dict(mapping["report"]),
            phenotype_column=str(phenotype_column) if phenotype_column else None,
            phenotype_kind=cast(
                Literal["auto", "categorical", "numeric"],
                association.get("phenotype_kind", "auto"),
            ),
            covariates=tuple(str(item) for item in association.get("covariates", [])),
            block_column=(
                str(association["block_column"])
                if enabled and association.get("block_column")
                else None
            ),
        )


def run_signature_scoring(
    bundle_archive: Path, config: SignatureScoringConfig, output_dir: Path
) -> dict[str, Any]:
    """Calculate one deterministic score per sample and mapped signature set."""
    bundle_digest = hashlib.sha256(bundle_archive.read_bytes()).hexdigest()
    if bundle_digest != config.mapping_report.get("expression_bundle_sha256"):
        raise ValueError("Expression Bundle checksum differs from the frozen mapping report.")
    bundle = load_bundle_assay(bundle_archive, config.assay)
    output_dir.mkdir(parents=True, exist_ok=False)
    feature_index = _unique_feature_index(bundle.feature_ids)
    warnings = [_CROSS_PLATFORM_WARNING, *_mapping_warnings(config.mapping_report)]
    set_results: list[dict[str, Any]] = []
    feature_rows: list[dict[str, Any]] = []
    for signature_set in config.mapping_report["sets"]:
        result, rows, set_warnings = _score_set(bundle, feature_index, signature_set, config.method)
        set_results.append(result)
        feature_rows.extend(rows)
        warnings.extend(set_warnings)
    association = (
        _associate_scores(bundle, set_results, config) if config.phenotype_column else None
    )
    summary = {
        "schema_version": "1.1.0",
        "analysis_id": config.analysis_id,
        "prepared_dataset_id": config.prepared_dataset_id,
        "method": config.method,
        "assay": config.assay,
        "formula": _method_formula(config.method),
        "signature_mapping": {
            "id": config.mapping_id,
            "report_sha256": config.mapping_report_sha256,
            "signature_definition_id": config.mapping_report["signature_definition_id"],
            "signature_definition_sha256": config.mapping_report["signature_definition_sha256"],
            "expression_bundle_sha256": bundle_digest,
            "mapping_coverage": config.mapping_report["mapping_coverage"],
            "requested_identifier_count": config.mapping_report["requested_identifier_count"],
            "mapped_identifier_count": config.mapping_report["mapped_identifier_count"],
            "missing_identifier_count": config.mapping_report["missing_identifier_count"],
            "ambiguous_identifier_count": config.mapping_report["ambiguous_identifier_count"],
            "duplicate_identifier_count": config.mapping_report["duplicate_identifier_count"],
        },
        "sample_count": len(bundle.sample_ids),
        "set_count": len(set_results),
        "sets": set_results,
        "phenotype_association": association,
        "warnings": warnings,
        "software": {
            "language": "Python",
            "language_version": platform.python_version(),
            "implementation": "transcriptforge_analysis.signature_scoring",
            "packages": {"numpy": np.__version__, "scipy": scipy.__version__},
        },
    }
    write_json_atomic(output_dir / "signature_scores.json", summary)
    _write_scores(output_dir / "signature_scores.tsv", set_results)
    _write_features(output_dir / "scored_features.tsv", feature_rows)
    _write_score_plot(output_dir / "signature_scores.svg", set_results)
    if association is not None:
        _write_associations(output_dir / "signature_associations.tsv", association)
        _write_association_plot(
            output_dir / "signature_associations.svg", association, set_results
        )
    write_json_atomic(output_dir / "result_manifest.json", _result_manifest(summary))
    write_dimension_reduction_report(
        output_dir,
        title="Signature scoring",
        analysis_id=config.analysis_id,
        assay=config.assay,
        summary={
            "Method": config.method,
            "Samples": len(bundle.sample_ids),
            "Signature sets": len(set_results),
            "Mapping coverage": f"{float(config.mapping_report['mapping_coverage']) * 100:.1f}%",
            "Mapped identifiers": config.mapping_report["mapped_identifier_count"],
            "Missing identifiers": config.mapping_report["missing_identifier_count"],
        },
        images=tuple(
            [("Per-sample signature scores", "signature_scores.svg")]
            + (
                [("Phenotype association", "signature_associations.svg")]
                if association is not None
                else []
            )
        ),
        notes=(
            _method_formula(config.method),
            _CROSS_PLATFORM_WARNING,
            "Scores are exploratory and are not clinically validated.",
        ),
    )
    return summary


def _associate_scores(
    bundle: BundleAssay,
    sets: list[dict[str, Any]],
    config: SignatureScoringConfig,
) -> dict[str, Any]:
    phenotype_column = str(config.phenotype_column)
    required = [phenotype_column, *config.covariates]
    if config.block_column:
        required.append(config.block_column)
    for column in required:
        if any(column not in bundle.metadata[sample_id] for sample_id in bundle.sample_ids):
            raise ValueError(f"Association variable '{column}' is absent from sample metadata.")
        if any(not bundle.metadata[sample_id][column].strip() for sample_id in bundle.sample_ids):
            raise ValueError(f"Association variable '{column}' contains missing values.")

    phenotype_values = [
        bundle.metadata[item][phenotype_column].strip() for item in bundle.sample_ids
    ]
    phenotype_kind = config.phenotype_kind
    if phenotype_kind == "auto":
        try:
            [float(value) for value in phenotype_values]
        except ValueError:
            phenotype_kind = "categorical"
        else:
            phenotype_kind = "numeric"

    nuisance_names = ["Intercept"]
    nuisance_columns = [np.ones(len(bundle.sample_ids), dtype=np.float64)]
    for column in config.covariates:
        names, columns = _association_term(
            column,
            [bundle.metadata[item][column].strip() for item in bundle.sample_ids],
            force_categorical=False,
        )
        nuisance_names.extend(names)
        nuisance_columns.extend(columns)
    if config.block_column:
        names, columns = _association_term(
            config.block_column,
            [bundle.metadata[item][config.block_column].strip() for item in bundle.sample_ids],
            force_categorical=True,
        )
        nuisance_names.extend(names)
        nuisance_columns.extend(columns)
    reduced = np.column_stack(nuisance_columns)

    levels: list[str] = []
    if phenotype_kind == "numeric":
        numbers = np.asarray([float(value) for value in phenotype_values], dtype=np.float64)
        phenotype_matrix = (numbers - np.mean(numbers)).reshape(-1, 1)
        phenotype_names = [phenotype_column]
    else:
        levels = sorted(set(phenotype_values))
        if len(levels) < 2:
            raise ValueError(f"Phenotype '{phenotype_column}' has fewer than two levels.")
        if any(phenotype_values.count(level) < 2 for level in levels):
            raise ValueError(
                f"Phenotype '{phenotype_column}' requires at least two samples in every group."
            )
        phenotype_names = [f"{phenotype_column}[{level}]" for level in levels[1:]]
        phenotype_matrix = np.column_stack(
            [
                np.asarray([value == level for value in phenotype_values], dtype=np.float64)
                for level in levels[1:]
            ]
        )
    full = np.column_stack((reduced, phenotype_matrix))
    if np.linalg.matrix_rank(full) < full.shape[1]:
        raise ValueError(
            "Phenotype association design is rank deficient; remove confounded adjustment terms."
        )
    residual_df = len(bundle.sample_ids) - full.shape[1]
    if residual_df < 1:
        raise ValueError("Phenotype association requires at least one residual degree of freedom.")

    associations = []
    for signature_set in sets:
        response = np.asarray(
            [float(item["score"]) for item in signature_set["scores"]], dtype=np.float64
        )
        coefficients, _, _, _ = np.linalg.lstsq(full, response, rcond=None)
        residuals = response - full @ coefficients
        residual_sum_squares = float(residuals @ residuals)
        phenotype_coefficient = coefficients[-phenotype_matrix.shape[1] :]
        correlation: float | None = None
        effect: float | None
        if phenotype_matrix.shape[1] == 1:
            covariance = np.linalg.pinv(full.T @ full)
            standard_error = float(
                np.sqrt(max(residual_sum_squares / residual_df * covariance[-1, -1], 0.0))
            )
            effect = float(phenotype_coefficient[0])
            if standard_error > np.finfo(np.float64).eps:
                statistic = effect / standard_error
                p_value = float(2 * t_distribution.sf(abs(statistic), residual_df))
            elif abs(effect) > np.finfo(np.float64).eps:
                statistic = float(np.copysign(np.finfo(np.float64).max, effect))
                p_value = 0.0
            else:
                statistic = 0.0
                p_value = 1.0
            test = (
                "adjusted_linear_regression"
                if phenotype_kind == "numeric"
                else "adjusted_two_group_comparison"
            )
            if (
                phenotype_kind == "numeric"
                and float(np.std(response)) > np.finfo(np.float64).eps
            ):
                correlation = float(pearsonr(numbers, response).statistic)
        else:
            reduced_coefficients, _, _, _ = np.linalg.lstsq(reduced, response, rcond=None)
            reduced_residuals = response - reduced @ reduced_coefficients
            reduced_sum_squares = float(reduced_residuals @ reduced_residuals)
            numerator_df = phenotype_matrix.shape[1]
            statistic = max(
                (reduced_sum_squares - residual_sum_squares) / numerator_df, 0.0
            ) / max(residual_sum_squares / residual_df, np.finfo(np.float64).tiny)
            statistic = min(statistic, float(np.finfo(np.float64).max))
            p_value = float(f_distribution.sf(statistic, numerator_df, residual_df))
            effect = None
            test = "adjusted_omnibus_group_comparison"
        group_summaries = [
            {
                "level": level,
                "sample_count": sum(value == level for value in phenotype_values),
                "score_mean": float(
                    np.mean(
                        [
                            response[index]
                            for index, value in enumerate(phenotype_values)
                            if value == level
                        ]
                    )
                ),
            }
            for level in levels
        ]
        associations.append(
            {
                "signature_id": signature_set["signature_id"],
                "signature_name": signature_set["name"],
                "test": test,
                "sample_count": len(bundle.sample_ids),
                "effect": effect,
                "statistic": float(statistic),
                "degrees_of_freedom": residual_df,
                "p_value": p_value,
                "adjusted_p_value": 1.0,
                "correlation": correlation,
                "group_summaries": group_summaries,
            }
        )
    for item, adjusted in zip(
        associations,
        _benjamini_hochberg([float(item["p_value"]) for item in associations]),
        strict=True,
    ):
        item["adjusted_p_value"] = adjusted
    formula_terms = [*config.covariates]
    if config.block_column:
        formula_terms.append(config.block_column)
    formula_terms.append(phenotype_column)
    return {
        "phenotype_column": phenotype_column,
        "phenotype_kind": phenotype_kind,
        "covariates": list(config.covariates),
        "block_column": config.block_column,
        "formula": "score ~ " + " + ".join(formula_terms),
        "design_matrix_columns": [*nuisance_names, *phenotype_names],
        "associations": associations,
    }


def _association_term(
    name: str, values: list[str], *, force_categorical: bool
) -> tuple[list[str], list[np.ndarray[Any, Any]]]:
    if not force_categorical:
        try:
            numbers = np.asarray([float(value) for value in values], dtype=np.float64)
        except ValueError:
            pass
        else:
            return [name], [numbers - np.mean(numbers)]
    levels = sorted(set(values))
    if len(levels) < 2:
        raise ValueError(f"Association variable '{name}' has fewer than two values.")
    return (
        [f"{name}[{level}]" for level in levels[1:]],
        [
            np.asarray([value == level for value in values], dtype=np.float64)
            for level in levels[1:]
        ],
    )


def _benjamini_hochberg(p_values: list[float]) -> list[float]:
    adjusted = [1.0] * len(p_values)
    running = 1.0
    ordered = enumerate(sorted(range(len(p_values)), key=p_values.__getitem__), 1)
    for rank, index in reversed(list(ordered)):
        running = min(running, p_values[index] * len(p_values) / rank)
        adjusted[index] = float(min(running, 1.0))
    return adjusted


def _unique_feature_index(feature_ids: list[str]) -> dict[str, int]:
    index: dict[str, int] = {}
    for position, feature_id in enumerate(feature_ids):
        if feature_id in index:
            raise ValueError(f"Expression assay contains duplicate feature ID '{feature_id}'.")
        index[feature_id] = position
    return index


def _score_set(
    bundle: BundleAssay,
    feature_index: dict[str, int],
    signature_set: dict[str, Any],
    method: SignatureMethod,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    entries = signature_set["mapped_entries"]
    if not entries:
        raise ValueError(f"Signature set '{signature_set['name']}' has no mapped features.")
    missing_from_assay = [
        entry["feature_id"] for entry in entries if entry["feature_id"] not in feature_index
    ]
    if missing_from_assay:
        raise ValueError(
            "Mapped features are absent from the selected assay: "
            + ", ".join(missing_from_assay[:10])
        )
    positions = np.asarray(
        [feature_index[entry["feature_id"]] for entry in entries], dtype=np.int64
    )
    values = bundle.matrix[positions, :].astype(np.float64, copy=False)
    used = np.ones(len(entries), dtype=bool)
    warnings: list[str] = []
    if method == "mean_expression":
        scores = np.mean(values, axis=0)
    elif method == "mean_z_score":
        standard_deviation = np.std(values, axis=1, ddof=1)
        used = standard_deviation > 0
        if not np.any(used):
            raise ValueError(
                f"Signature set '{signature_set['name']}' has no variable mapped features."
            )
        excluded = int(np.sum(~used))
        if excluded:
            warnings.append(
                f"{signature_set['name']}: excluded {excluded} constant feature(s) "
                "from mean z-score calculation."
            )
        centered = values[used] - np.mean(values[used], axis=1, keepdims=True)
        scores = np.mean(centered / standard_deviation[used, None], axis=0)
    elif method == "weighted_linear":
        if any("weight" not in entry for entry in entries):
            raise ValueError(
                f"Signature set '{signature_set['name']}' lacks weights for linear scoring."
            )
        weights = np.asarray([float(entry["weight"]) for entry in entries])
        scores = weights @ values
    else:
        percentile_ranks = rankdata(bundle.matrix, axis=0, method="average") / len(
            bundle.feature_ids
        )
        scores = np.mean(percentile_ranks[positions, :], axis=0)
    if not np.all(np.isfinite(scores)):
        raise ValueError(f"Signature set '{signature_set['name']}' produced non-finite scores.")
    feature_rows = [
        {
            "signature_id": signature_set["signature_id"],
            "signature_name": signature_set["name"],
            "identifier": entry["identifier"],
            "feature_id": entry["feature_id"],
            "weight": entry.get("weight"),
            "used": bool(used[index]),
            "exclusion_reason": "" if used[index] else "constant_across_samples",
        }
        for index, entry in enumerate(entries)
    ]
    score_values = [float(value) for value in scores]
    result = {
        "signature_id": signature_set["signature_id"],
        "name": signature_set["name"],
        "requested_identifier_count": signature_set["requested_identifier_count"],
        "mapped_identifier_count": signature_set["mapped_identifier_count"],
        "scored_feature_count": int(np.sum(used)),
        "excluded_constant_feature_count": int(np.sum(~used)),
        "mapping_coverage": signature_set["mapping_coverage"],
        "score_minimum": min(score_values),
        "score_maximum": max(score_values),
        "score_mean": float(np.mean(scores)),
        "scores": [
            {
                "sample_id": sample_id,
                "score": score_values[index],
                "metadata": bundle.metadata[sample_id],
            }
            for index, sample_id in enumerate(bundle.sample_ids)
        ],
    }
    return result, feature_rows, warnings


def _mapping_warnings(report: dict[str, Any]) -> list[str]:
    warnings = []
    for label, field in (
        ("missing", "missing_identifier_count"),
        ("ambiguous", "ambiguous_identifier_count"),
        ("duplicate", "duplicate_identifier_count"),
    ):
        count = int(report[field])
        if count:
            warnings.append(f"Mapping report contains {count} {label} identifier(s).")
    return warnings


def _method_formula(method: SignatureMethod) -> str:
    return {
        "mean_expression": "Arithmetic mean of mapped log-expression values per sample.",
        "mean_z_score": (
            "Arithmetic mean of mapped gene z-scores, standardized across samples with "
            "sample standard deviation; constant genes are excluded."
        ),
        "weighted_linear": (
            "Unnormalized sum of weight multiplied by mapped log expression per sample."
        ),
        "rank_based": (
            "Arithmetic mean of mapped-gene within-sample percentile ranks across all assay genes."
        ),
    }[method]


def _write_scores(path: Path, sets: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        output = csv.writer(handle, delimiter="\t", lineterminator="\n")
        output.writerow(["sample_id", "signature_id", "signature_name", "score"])
        for signature_set in sets:
            for item in signature_set["scores"]:
                output.writerow(
                    [
                        item["sample_id"],
                        signature_set["signature_id"],
                        signature_set["name"],
                        format(float(item["score"]), ".17g"),
                    ]
                )


def _write_features(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        output = csv.writer(handle, delimiter="\t", lineterminator="\n")
        output.writerow(
            [
                "signature_id",
                "signature_name",
                "identifier",
                "feature_id",
                "weight",
                "used",
                "exclusion_reason",
            ]
        )
        for row in rows:
            output.writerow(
                [
                    row["signature_id"],
                    row["signature_name"],
                    row["identifier"],
                    row["feature_id"],
                    "" if row["weight"] is None else format(float(row["weight"]), ".17g"),
                    str(row["used"]).upper(),
                    row["exclusion_reason"],
                ]
            )


def _write_associations(path: Path, association: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        output = csv.writer(handle, delimiter="\t", lineterminator="\n")
        output.writerow(
            [
                "signature_id",
                "signature_name",
                "phenotype",
                "phenotype_kind",
                "test",
                "sample_count",
                "effect",
                "correlation",
                "statistic",
                "degrees_of_freedom",
                "p_value",
                "adjusted_p_value",
            ]
        )
        for item in association["associations"]:
            output.writerow(
                [
                    item["signature_id"],
                    item["signature_name"],
                    association["phenotype_column"],
                    association["phenotype_kind"],
                    item["test"],
                    item["sample_count"],
                    "" if item["effect"] is None else format(item["effect"], ".17g"),
                    (
                        ""
                        if item["correlation"] is None
                        else format(item["correlation"], ".17g")
                    ),
                    format(item["statistic"], ".17g"),
                    item["degrees_of_freedom"],
                    format(item["p_value"], ".17g"),
                    format(item["adjusted_p_value"], ".17g"),
                ]
            )


def _write_association_plot(
    path: Path, association: dict[str, Any], sets: list[dict[str, Any]]
) -> None:
    width = 960
    panel_height = 300
    height = 70 + panel_height * len(sets)
    phenotype = association["phenotype_column"]
    kind = association["phenotype_kind"]
    colors = ("#155e75", "#7c3aed", "#d97706", "#be123c", "#15803d")
    panels: list[str] = []
    for panel_index, signature_set in enumerate(sets):
        top = 55 + panel_index * panel_height
        scores = signature_set["scores"]
        values = [float(item["score"]) for item in scores]
        low, high = min(values), max(values)
        if low == high:
            low -= 1
            high += 1

        def y(
            value: float,
            panel_top: float = top,
            minimum: float = low,
            maximum: float = high,
        ) -> float:
            return panel_top + 220 - (value - minimum) / (maximum - minimum) * 180

        panels.append(
            f"<text x='80' y='{top}' font-size='18' font-weight='700'>"
            f"{html.escape(str(signature_set['name']))}</text>"
        )
        panels.append(
            f"<line x1='80' y1='{top + 35}' x2='80' y2='{top + 220}' stroke='#94a3b8'/>"
        )
        panels.append(
            f"<line x1='80' y1='{top + 220}' x2='920' y2='{top + 220}' stroke='#94a3b8'/>"
        )
        if kind == "categorical":
            levels = sorted({str(item["metadata"][phenotype]) for item in scores})
            for level_index, level in enumerate(levels):
                center = 120 + (level_index + 0.5) / len(levels) * 760
                level_scores = [
                    float(item["score"])
                    for item in scores
                    if str(item["metadata"][phenotype]) == level
                ]
                mean = float(np.mean(level_scores))
                panels.append(
                    f"<line x1='{center - 32:.2f}' y1='{y(mean):.2f}' x2='{center + 32:.2f}' "
                    "y2='%.2f' stroke='#0f172a' stroke-width='3'/>" % y(mean)
                )
                for point_index, value in enumerate(level_scores):
                    jitter = ((point_index * 37) % 41 - 20) * 0.9
                    panels.append(
                        f"<circle cx='{center + jitter:.2f}' cy='{y(value):.2f}' r='5' "
                        f"fill='{colors[level_index % len(colors)]}' fill-opacity='.82'/>"
                    )
                panels.append(
                    f"<text x='{center:.2f}' y='{top + 244}' text-anchor='middle' font-size='12'>"
                    f"{html.escape(level)} (n={len(level_scores)})</text>"
                )
        else:
            numeric = [float(item["metadata"][phenotype]) for item in scores]
            x_low, x_high = min(numeric), max(numeric)
            if x_low == x_high:
                x_low -= 1
                x_high += 1

            def x(
                value: float, minimum: float = x_low, maximum: float = x_high
            ) -> float:
                return 100 + (value - minimum) / (maximum - minimum) * 800

            slope, intercept = np.polyfit(numeric, values, 1)
            panels.append(
                f"<line x1='{x(x_low):.2f}' y1='{y(slope * x_low + intercept):.2f}' "
                f"x2='{x(x_high):.2f}' y2='{y(slope * x_high + intercept):.2f}' "
                "stroke='#be123c' stroke-width='2'/>"
            )
            for x_value, score in zip(numeric, values, strict=True):
                panels.append(
                    f"<circle cx='{x(x_value):.2f}' cy='{y(score):.2f}' r='5' "
                    "fill='#155e75' fill-opacity='.82'/>"
                )
            panels.append(
                f"<text x='500' y='{top + 244}' text-anchor='middle' font-size='12'>"
                f"{html.escape(phenotype)}</text>"
            )
    path.write_text(
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' "
        f"viewBox='0 0 {width} {height}' role='img' aria-label='Signature phenotype association'>"
        "<style>text{font-family:system-ui,sans-serif;fill:#17323a}</style>"
        "<rect width='100%' height='100%' fill='white'/>"
        f"<text x='480' y='28' text-anchor='middle' font-size='22' font-weight='700'>"
        f"Scores by {html.escape(phenotype)}</text>{''.join(panels)}</svg>\n",
        encoding="utf-8",
    )


def _write_score_plot(path: Path, sets: list[dict[str, Any]]) -> None:
    width, height, left, bottom = 960, 560, 80, 95
    all_scores = [float(item["score"]) for group in sets for item in group["scores"]]
    minimum, maximum = min(all_scores), max(all_scores)
    if minimum == maximum:
        minimum -= 1.0
        maximum += 1.0
    margin = (maximum - minimum) * 0.08
    minimum -= margin
    maximum += margin
    samples = [item["sample_id"] for item in sets[0]["scores"]]
    colors = ("#155e75", "#7c3aed", "#d97706", "#be123c", "#15803d")

    def x(index: int) -> float:
        return left + (index + 0.5) / len(samples) * (width - left - 30)

    def y(value: float) -> float:
        return 40 + (maximum - value) / (maximum - minimum) * (height - bottom - 40)

    circles = []
    for set_index, group in enumerate(sets):
        offset = (set_index - (len(sets) - 1) / 2) * 5
        for sample_index, item in enumerate(group["scores"]):
            circles.append(
                f"<circle cx='{x(sample_index) + offset:.2f}' cy='{y(float(item['score'])):.2f}' "
                f"r='5' fill='{colors[set_index % len(colors)]}'><title>"
                f"{html.escape(str(group['name']))}; {html.escape(str(item['sample_id']))}: "
                f"{float(item['score']):.5g}</title></circle>"
            )
    labels = "".join(
        f"<text x='{x(index):.2f}' y='{height - bottom + 18}' font-size='10' "
        f"text-anchor='end' transform='rotate(-55 {x(index):.2f} {height - bottom + 18})'>"
        f"{html.escape(sample)}</text>"
        for index, sample in enumerate(samples)
    )
    legend = "".join(
        f"<circle cx='{left + index * 180}' cy='{height - 18}' r='5' "
        f"fill='{colors[index % len(colors)]}'/><text x='{left + 10 + index * 180}' "
        f"y='{height - 14}' font-size='12'>{html.escape(str(group['name']))}</text>"
        for index, group in enumerate(sets[:5])
    )
    path.write_text(
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' "
        f"viewBox='0 0 {width} {height}' role='img' aria-label='Per-sample signature scores'>"
        "<style>text{font-family:system-ui,sans-serif;fill:#17323a}</style>"
        "<rect width='100%' height='100%' fill='white'/>"
        f"<text x='{width / 2}' y='28' text-anchor='middle' font-size='22' font-weight='700'>"
        "Per-sample signature scores</text>"
        f"<line x1='{left}' y1='40' x2='{left}' y2='{height - bottom}' stroke='#94a3b8'/>"
        f"<line x1='{left}' y1='{height - bottom}' x2='{width - 30}' "
        f"y2='{height - bottom}' stroke='#94a3b8'/>{''.join(circles)}{labels}{legend}</svg>\n",
        encoding="utf-8",
    )


def _result_manifest(summary: dict[str, Any]) -> dict[str, Any]:
    mapping = summary["signature_mapping"]
    association = summary["phenotype_association"]
    sections = [
        {
            "id": "signature-scores",
            "title": "Per-sample signature scores",
            "items": [
                {
                    "type": "plotly_json",
                    "title": "Signature scores",
                    "path": "signature_scores.json",
                },
                {
                    "type": "image",
                    "title": "Static signature scores",
                    "path": "signature_scores.svg",
                },
                {
                    "type": "table",
                    "title": "Per-sample scores",
                    "path": "signature_scores.tsv",
                },
            ],
        }
    ]
    downloads = [
        {
            "type": "table",
            "title": "Per-sample scores",
            "path": "signature_scores.tsv",
        },
        {
            "type": "table",
            "title": "Final scored features",
            "path": "scored_features.tsv",
        },
        {
            "type": "image",
            "title": "Signature scores (SVG)",
            "path": "signature_scores.svg",
        },
    ]
    if association is not None:
        sections.append(
            {
                "id": "phenotype-association",
                "title": "Phenotype association",
                "items": [
                    {
                        "type": "image",
                        "title": "Phenotype-aware signature scores",
                        "path": "signature_associations.svg",
                    },
                    {
                        "type": "table",
                        "title": "Phenotype association statistics",
                        "path": "signature_associations.tsv",
                    },
                ],
            }
        )
        downloads.extend(
            [
                {
                    "type": "table",
                    "title": "Phenotype association statistics",
                    "path": "signature_associations.tsv",
                },
                {
                    "type": "image",
                    "title": "Phenotype association (SVG)",
                    "path": "signature_associations.svg",
                },
            ]
        )
    downloads.extend(
        [
            {"type": "html", "title": "Signature report", "path": "report.html"},
            {"type": "file", "title": "Quarto report source", "path": "report.qmd"},
        ]
    )
    return {
        "schema_version": "1.0.0",
        "analysis_type": "signature",
        "title": "Signature scoring",
        "summary_metrics": [
            {"label": "Samples", "value": summary["sample_count"]},
            {"label": "Signature sets", "value": summary["set_count"]},
            {"label": "Method", "value": summary["method"]},
            {"label": "Mapping coverage", "value": mapping["mapping_coverage"]},
            {"label": "Mapped identifiers", "value": mapping["mapped_identifier_count"]},
            {"label": "Missing identifiers", "value": mapping["missing_identifier_count"]},
        ],
        "sections": sections,
        "downloads": downloads,
        "warnings": summary["warnings"],
    }
