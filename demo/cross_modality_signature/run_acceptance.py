"""Deterministic cross-modality acceptance for one frozen weighted signature."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import tarfile
from pathlib import Path
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator
from transcriptforge_analysis.signature_scoring import (
    SignatureScoringConfig,
    run_signature_scoring,
)

ROOT = Path(__file__).parents[2]
FIXTURE = Path(__file__).parent
SIGNATURE_PATH = FIXTURE / "response_signature.tsv"
WARNING = (
    "Raw signature scores must not be compared across RNA-seq, microarray, cohorts, or "
    "preprocessing pipelines; compare prespecified within-dataset direction, ranking, "
    "association, or standardized effects."
)


def run_acceptance(output_dir: Path) -> dict[str, Any]:
    """Build both platform fixtures, score them, and enforce cross-platform criteria."""
    output_dir.mkdir(parents=True, exist_ok=False)
    definition_sha256, entries = _read_signature(SIGNATURE_PATH)
    criteria = {
        "minimum_mapping_coverage": 1.0,
        "maximum_adjusted_p_value": 0.05,
        "minimum_auc": 0.95,
        "require_direction_concordance": True,
        "require_distinct_raw_scales": True,
    }
    cohort_results: list[dict[str, Any]] = []
    for modality in ("bulk_rnaseq", "microarray"):
        cohort_dir = output_dir / modality
        cohort_dir.mkdir()
        archive = cohort_dir / "expression_bundle.tar.gz"
        bundle_sha256 = _build_bundle(archive, modality, [item[0] for item in entries])
        mapping_report = _mapping_report(definition_sha256, bundle_sha256, entries)
        mapping_bytes = _json_bytes(mapping_report)
        mapping_sha256 = hashlib.sha256(mapping_bytes).hexdigest()
        config = SignatureScoringConfig(
            analysis_id=f"cross-modality-{modality}",
            prepared_dataset_id=f"prepared-cross-modality-{modality}",
            method="weighted_linear",
            assay="log_expression",
            mapping_id=f"mapping-cross-modality-{modality}",
            mapping_report_sha256=mapping_sha256,
            mapping_report=mapping_report,
            phenotype_column="condition",
            phenotype_kind="categorical",
        )
        summary = run_signature_scoring(archive, config, cohort_dir / "scores")
        cohort_results.append(
            _cohort_result(modality, bundle_sha256, mapping_sha256, summary, criteria)
        )

    ranges = [item["score_maximum"] - item["score_minimum"] for item in cohort_results]
    raw_scales_distinct = max(ranges) / min(ranges) >= 2.0
    concordance = {
        "same_signature_sha256": all(
            item["signature_definition_sha256"] == definition_sha256 for item in cohort_results
        ),
        "direction_concordant": all(item["direction"] == "positive" for item in cohort_results),
        "both_meet_mapping_threshold": all(
            item["mapping_coverage"] >= criteria["minimum_mapping_coverage"]
            for item in cohort_results
        ),
        "both_meet_fdr_threshold": all(
            item["adjusted_p_value"] <= criteria["maximum_adjusted_p_value"]
            for item in cohort_results
        ),
        "both_meet_auc_threshold": all(
            item["auc"] >= criteria["minimum_auc"] for item in cohort_results
        ),
        "raw_scales_distinct": raw_scales_distinct,
    }
    passed = all(concordance.values()) and all(item["passed"] for item in cohort_results)
    result = {
        "schema_version": "1.0.0",
        "signature_definition": {
            "source": str(SIGNATURE_PATH.relative_to(ROOT)),
            "sha256": definition_sha256,
            "identifier_type": "ensembl_gene_id",
            "signature_id": "cross_modality_response",
            "feature_count": len(entries),
        },
        "method": "weighted_linear",
        "phenotype": {
            "column": "condition",
            "numerator": "treated",
            "denominator": "control",
            "expected_direction": "positive",
        },
        "interpretation_boundary": {
            "raw_score_scale_comparable": False,
            "permitted_comparisons": [
                "mapping_coverage",
                "within_cohort_direction",
                "within_cohort_rank_discrimination",
                "standardized_effect",
            ],
            "warning": WARNING,
        },
        "criteria": criteria,
        "cohorts": cohort_results,
        "concordance": concordance,
        "passed": passed,
    }
    schema = json.loads(
        (ROOT / "schemas/cross_modality_signature_acceptance.schema.json").read_text()
    )
    Draft202012Validator(schema).validate(result)
    (output_dir / "cross_modality_acceptance.json").write_bytes(_json_bytes(result))
    if not passed:
        raise AssertionError("Cross-modality signature acceptance criteria were not met.")
    return result


def _read_signature(path: Path) -> tuple[str, list[tuple[str, float]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        entries = [(str(row["gene_id"]), float(row["weight"])) for row in reader]
    if len(entries) < 2 or len({item[0] for item in entries}) != len(entries):
        raise ValueError("Cross-modality signature must contain unique weighted identifiers.")
    return hashlib.sha256(path.read_bytes()).hexdigest(), entries


def _build_bundle(archive: Path, modality: str, feature_ids: list[str]) -> str:
    sample_ids = [
        f"{modality}_{condition}_{replicate}"
        for condition in ("control", "treated")
        for replicate in range(1, 5)
    ]
    conditions = ["control"] * 4 + ["treated"] * 4
    if modality == "bulk_rnaseq":
        counts = _rna_counts(len(feature_ids))
        library_sizes = np.sum(counts, axis=0)
        log_expression = np.log2(counts / library_sizes[None, :] * 1_000_000 + 1)
        assays = {
            "raw_counts": _matrix_tsv(feature_ids, sample_ids, counts, integer=True),
            "log_expression": _matrix_tsv(feature_ids, sample_ids, log_expression),
        }
    else:
        log_expression = _microarray_expression(len(feature_ids))
        probe_ids = [f"probe_{index:04d}" for index in range(1, len(feature_ids) + 1)]
        assays = {
            "log_expression": _matrix_tsv(feature_ids, sample_ids, log_expression),
            "probe_expression": _matrix_tsv(probe_ids, sample_ids, log_expression),
        }
    compressed_assays = {name: _gzip_bytes(payload) for name, payload in assays.items()}
    files: dict[str, bytes] = {
        "sample_metadata.tsv": _metadata_tsv(sample_ids, conditions),
        "feature_metadata.tsv": _feature_metadata_tsv(feature_ids),
        "qc/qc_metrics.tsv": b"sample_id\tstatus\n"
        + b"".join(f"{sample}\tPASS\n".encode() for sample in sample_ids),
        "qc/sample_flags.tsv": b"sample_id\tstatus\treasons\n"
        + b"".join(f"{sample}\tPASS\t\n".encode() for sample in sample_ids),
        "provenance/parameters.json": _json_bytes(
            {
                "fixture": "cross_modality_signature",
                "modality": modality,
                "transformation": "log2_counts_per_million_plus_one"
                if modality == "bulk_rnaseq"
                else "synthetic_rma_like_log2_expression",
            }
        ),
        "provenance/input_checksums.tsv": b"role\tpath\tsha256\n",
        "provenance/software_versions.yml": b"transcriptforge_fixture: '1.0.0'\n",
    }
    assay_declarations = []
    for name, payload in compressed_assays.items():
        relative_path = f"assays/{name}.tsv.gz"
        files[relative_path] = payload
        assay_declarations.append(
            {
                "name": name,
                "path": relative_path,
                "value_type": "nonnegative_integer" if name == "raw_counts" else "continuous",
                "scale": "linear" if name == "raw_counts" else "log2",
                "feature_level": "probe" if name == "probe_expression" else "gene",
                "recommended_for": ["differential_expression"]
                if name == "raw_counts" or name == "probe_expression"
                else ["dimension_reduction", "classifier", "signature_analysis"],
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest: dict[str, Any] = {
        "schema_version": "1.0.0",
        "dataset_id": f"cross-modality-{modality}",
        "prepared_dataset_id": f"prepared-cross-modality-{modality}",
        "organism": "Homo sapiens",
        "genome_build": "GRCh38.p14",
        "annotation_release": "synthetic acceptance fixture 1.0.0",
        "primary_feature_id": "ensembl_gene_id",
        "sample_count": len(sample_ids),
        "feature_count": len(feature_ids),
        "sample_metadata": "sample_metadata.tsv",
        "feature_metadata": "feature_metadata.tsv",
        "assays": assay_declarations,
        "qc": {
            "status": "PASS",
            "metrics": "qc/qc_metrics.tsv",
            "sample_flags": "qc/sample_flags.tsv",
        },
        "provenance": {
            "parameters": "provenance/parameters.json",
            "input_checksums": "provenance/input_checksums.tsv",
            "software_versions": "provenance/software_versions.yml",
        },
    }
    if modality == "microarray":
        files["mappings/probe_mapping.tsv"] = (
            b"probe_id\tensembl_gene_id\tmapping_status\n"
            + b"".join(
                f"probe_{index:04d}\t{feature_id}\tmapped\n".encode()
                for index, feature_id in enumerate(feature_ids, 1)
            )
        )
        manifest["microarray"] = {
            "platform_id": "transcriptforge_cross_modality_array",
            "platform_definition_sha256": "a" * 64,
            "adapter_version": "1.0.0",
            "normalization_engine": "oligo",
            "normalization_method": "rma",
            "rma_target": "probeset",
            "annotation_package": "synthetic.acceptance.annotation",
            "annotation_confidence": "explicit_platform_adapter",
            "aggregation_method": "highest_mad",
            "probe_expression_assay": "probe_expression",
            "probe_mapping": "mappings/probe_mapping.tsv",
        }
    schema = json.loads((ROOT / "schemas/expression_bundle.schema.json").read_text())
    Draft202012Validator(schema).validate(manifest)
    files["bundle_manifest.json"] = _json_bytes(manifest)
    _write_archive(archive, files)
    return hashlib.sha256(archive.read_bytes()).hexdigest()


def _rna_counts(feature_count: int) -> np.ndarray[Any, Any]:
    baseline = np.asarray([90, 105, 120, 135, 90, 105, 120, 135], dtype=np.float64)
    direction = np.asarray([1] * 4 + [-1] * 4, dtype=np.float64)
    groups = np.asarray([0] * 4 + [1] * 4, dtype=np.float64)
    library_factors = np.asarray([0.92, 1.04, 1.1, 0.97, 1.03, 0.95, 1.08, 1.0])
    values = baseline[:, None] * library_factors[None, :]
    values *= np.power(4.0, direction[:, None] * groups[None, :])
    noise = np.random.default_rng(20260718).normal(1, 0.025, (feature_count, 8))
    return np.maximum(np.rint(values * noise), 1).astype(np.int64)


def _microarray_expression(feature_count: int) -> np.ndarray[Any, Any]:
    baseline = np.linspace(6.2, 7.6, feature_count)
    direction = np.asarray([1] * 4 + [-1] * 4, dtype=np.float64)
    groups = np.asarray([0] * 4 + [1] * 4, dtype=np.float64)
    noise = np.random.default_rng(20260719).normal(0, 0.045, (feature_count, 8))
    return baseline[:, None] + direction[:, None] * groups[None, :] * 0.62 + noise


def _mapping_report(
    definition_sha256: str, bundle_sha256: str, entries: list[tuple[str, float]]
) -> dict[str, Any]:
    return {
        "signature_definition_id": "cross-modality-response-definition",
        "signature_definition_sha256": definition_sha256,
        "expression_bundle_sha256": bundle_sha256,
        "mapping_coverage": 1.0,
        "requested_identifier_count": len(entries),
        "mapped_identifier_count": len(entries),
        "missing_identifier_count": 0,
        "ambiguous_identifier_count": 0,
        "duplicate_identifier_count": 0,
        "sets": [
            {
                "signature_id": "cross_modality_response",
                "name": "Cross-modality treatment response",
                "requested_identifier_count": len(entries),
                "mapped_identifier_count": len(entries),
                "mapping_coverage": 1.0,
                "mapped_entries": [
                    {"identifier": feature_id, "feature_id": feature_id, "weight": weight}
                    for feature_id, weight in entries
                ],
            }
        ],
    }


def _cohort_result(
    modality: str,
    bundle_sha256: str,
    mapping_sha256: str,
    summary: dict[str, Any],
    criteria: dict[str, Any],
) -> dict[str, Any]:
    signature_set = summary["sets"][0]
    association = summary["phenotype_association"]["associations"][0]
    control = [
        float(item["score"])
        for item in signature_set["scores"]
        if item["metadata"]["condition"] == "control"
    ]
    treated = [
        float(item["score"])
        for item in signature_set["scores"]
        if item["metadata"]["condition"] == "treated"
    ]
    effect = float(np.mean(treated) - np.mean(control))
    pooled_variance = (
        (len(control) - 1) * float(np.var(control, ddof=1))
        + (len(treated) - 1) * float(np.var(treated, ddof=1))
    ) / (len(control) + len(treated) - 2)
    standardized = effect / math.sqrt(pooled_variance)
    auc = sum(
        1.0 if treated_score > control_score else 0.5 if treated_score == control_score else 0.0
        for treated_score in treated
        for control_score in control
    ) / (len(treated) * len(control))
    direction = "positive" if effect > 0 else "negative" if effect < 0 else "zero"
    passed = (
        summary["signature_mapping"]["mapping_coverage"] >= criteria["minimum_mapping_coverage"]
        and association["adjusted_p_value"] <= criteria["maximum_adjusted_p_value"]
        and auc >= criteria["minimum_auc"]
        and direction == "positive"
    )
    return {
        "cohort_id": f"synthetic_{modality}_cohort",
        "modality": modality,
        "prepared_dataset_id": summary["prepared_dataset_id"],
        "bundle_sha256": bundle_sha256,
        "mapping_report_sha256": mapping_sha256,
        "signature_definition_sha256": summary["signature_mapping"]["signature_definition_sha256"],
        "mapping_coverage": summary["signature_mapping"]["mapping_coverage"],
        "sample_count": summary["sample_count"],
        "score_minimum": signature_set["score_minimum"],
        "score_maximum": signature_set["score_maximum"],
        "raw_group_effect": effect,
        "standardized_mean_difference": standardized,
        "auc": auc,
        "p_value": association["p_value"],
        "adjusted_p_value": association["adjusted_p_value"],
        "direction": direction,
        "passed": passed,
    }


def _matrix_tsv(
    feature_ids: list[str],
    sample_ids: list[str],
    values: np.ndarray[Any, Any],
    *,
    integer: bool = False,
) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    writer.writerow(["feature_id", *sample_ids])
    for feature_id, row in zip(feature_ids, values, strict=True):
        formatted = [str(int(value)) if integer else format(float(value), ".10g") for value in row]
        writer.writerow([feature_id, *formatted])
    return output.getvalue().encode()


def _metadata_tsv(sample_ids: list[str], conditions: list[str]) -> bytes:
    rows = ["sample_id\tcondition\tplatform_batch"]
    rows.extend(
        f"{sample_id}\t{condition}\tbatch_{index % 2 + 1}"
        for index, (sample_id, condition) in enumerate(zip(sample_ids, conditions, strict=True))
    )
    return ("\n".join(rows) + "\n").encode()


def _feature_metadata_tsv(feature_ids: list[str]) -> bytes:
    rows = ["feature_id\tensembl_gene_id\tgene_symbol\tmapping_status"]
    rows.extend(
        f"{feature_id}\t{feature_id}\tCM{index}\tmapped"
        for index, feature_id in enumerate(feature_ids, 1)
    )
    return ("\n".join(rows) + "\n").encode()


def _gzip_bytes(payload: bytes) -> bytes:
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as handle:
        handle.write(payload)
    return output.getvalue()


def _write_archive(path: Path, files: dict[str, bytes]) -> None:
    with (
        path.open("wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for relative_path, payload in sorted(files.items()):
            member = tarfile.TarInfo(f"expression_bundle/{relative_path}")
            member.size = len(payload)
            member.mtime = 0
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(payload))


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    result = run_acceptance(arguments.output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
