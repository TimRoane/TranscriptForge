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
from scipy.stats import rankdata  # type: ignore[import-untyped]

from transcriptforge_analysis.matrix_validation import write_json_atomic
from transcriptforge_analysis.pca import BundleAssay, load_bundle_assay
from transcriptforge_analysis.reporting import write_dimension_reduction_report

SignatureMethod = Literal["mean_expression", "mean_z_score", "weighted_linear", "rank_based"]


@dataclass(frozen=True, slots=True)
class SignatureScoringConfig:
    analysis_id: str
    prepared_dataset_id: str
    method: SignatureMethod
    assay: str
    mapping_id: str
    mapping_report_sha256: str
    mapping_report: dict[str, Any]

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
        return cls(
            analysis_id=str(payload["analysis_id"]),
            prepared_dataset_id=str(payload["prepared_dataset_id"]),
            method=cast(SignatureMethod, method),
            assay=assay,
            mapping_id=str(mapping["id"]),
            mapping_report_sha256=str(mapping["report_sha256"]),
            mapping_report=dict(mapping["report"]),
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
    warnings = _mapping_warnings(config.mapping_report)
    set_results: list[dict[str, Any]] = []
    feature_rows: list[dict[str, Any]] = []
    for signature_set in config.mapping_report["sets"]:
        result, rows, set_warnings = _score_set(bundle, feature_index, signature_set, config.method)
        set_results.append(result)
        feature_rows.extend(rows)
        warnings.extend(set_warnings)
    summary = {
        "schema_version": "1.0.0",
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
        images=(("Per-sample signature scores", "signature_scores.svg"),),
        notes=(
            _method_formula(config.method),
            "Scores are exploratory, cohort- and assay-dependent, and are not clinically "
            "validated.",
        ),
    )
    return summary


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
        "sections": [
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
        ],
        "downloads": [
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
            {"type": "html", "title": "Signature report", "path": "report.html"},
            {"type": "file", "title": "Quarto report source", "path": "report.qmd"},
        ],
        "warnings": summary["warnings"],
    }
