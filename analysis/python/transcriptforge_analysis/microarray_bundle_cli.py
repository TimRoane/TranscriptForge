"""Assemble oligo RMA outputs into a canonical microarray Expression Bundle."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from transcriptforge_analysis.expression_bundle import (
    BundleConfig,
    _archive_bundle,
    build_expression_bundle,
)
from transcriptforge_analysis.matrix_validation import ValidationConfig, write_json_atomic

ROOT = Path(__file__).parents[3]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gzip_copy(source: Path, target: Path) -> None:
    with (
        source.open("rb") as input_file,
        target.open("wb") as raw_output,
        gzip.GzipFile(fileobj=raw_output, mode="wb", filename="", mtime=0) as output,
    ):
        shutil.copyfileobj(input_file, output)


def build_microarray_bundle(
    ingestion_path: Path,
    gene_expression: Path,
    probe_expression: Path,
    gene_feature_metadata: Path,
    probe_mapping: Path,
    array_qc_metrics: Path,
    sample_flags: Path,
    array_qc_summary: Path,
    r_output_dir: Path,
    metadata: Path,
    output_dir: Path,
    prepared_dataset_id: str,
    prepared_version: int,
) -> None:
    ingestion = dict(json.loads(ingestion_path.read_text(encoding="utf-8")))
    platform = dict(ingestion["platform"])
    validation = ValidationConfig(
        dataset_id=str(ingestion["dataset_id"]),
        name=str(platform["array_design"]),
        matrix_path=gene_expression,
        metadata_path=metadata,
        matrix_orientation="features_by_samples",
        feature_id_column="feature_id",
        sample_id_column="sample_id",
        value_type="normalized_expression",
        modality="microarray",
        source_kind="affymetrix_cel",
        organism=str(ingestion["organism"]),
        genome_build="GRCh38",
        annotation_release=str(platform["annotation"]["package"]),
        feature_id_type="ensembl_gene_id",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = build_expression_bundle(
        BundleConfig(
            validation=validation,
            prepared_dataset_id=prepared_dataset_id,
            prepared_version=prepared_version,
            strip_ensembl_version=True,
        ),
        output_dir,
    )
    bundle = output_dir / "expression_bundle"
    assays_dir = bundle / "assays"
    qc_dir = bundle / "qc"
    mappings_dir = bundle / "mappings"
    provenance_dir = bundle / "provenance"

    normalized_path = assays_dir / "normalized_expression.tsv.gz"
    log_path = assays_dir / "log_expression.tsv.gz"
    normalized_path.replace(log_path)
    probe_target = assays_dir / "probe_expression.tsv.gz"
    _gzip_copy(probe_expression, probe_target)
    shutil.copyfile(gene_feature_metadata, bundle / "feature_metadata.tsv")
    shutil.copyfile(probe_mapping, mappings_dir / "probe_mapping.tsv")
    shutil.copyfile(array_qc_metrics, qc_dir / "array_qc_metrics.tsv")
    shutil.copyfile(sample_flags, qc_dir / "sample_flags.tsv")
    (qc_dir / "qc_metrics.tsv").unlink(missing_ok=True)
    (qc_dir / "plots/library_sizes.svg").unlink(missing_ok=True)
    plots_target = qc_dir / "plots"
    for plot in sorted((r_output_dir / "plots").glob("*.svg")):
        shutil.copyfile(plot, plots_target / plot.name)
    shutil.copyfile(r_output_dir / "parameters.json", provenance_dir / "parameters.json")
    shutil.copyfile(
        r_output_dir / "software_versions.yml", provenance_dir / "software_versions.yml"
    )
    shutil.copyfile(r_output_dir / "session_info.txt", provenance_dir / "session_info.txt")
    _write_input_checksums(ingestion, provenance_dir / "input_checksums.tsv")

    qc_summary = dict(json.loads(array_qc_summary.read_text(encoding="utf-8")))
    write_json_atomic(output_dir / "qc_summary.json", qc_summary)
    mapping_summary = {
        **summary.to_dict(),
        "probe_count": int(qc_summary["probe_count"]),
        "gene_count": int(qc_summary["gene_count"]),
        "aggregation_method": ingestion["aggregation_method"],
        "probe_mapping_path": "mappings/probe_mapping.tsv",
    }
    write_json_atomic(output_dir / "feature_mapping_summary.json", mapping_summary)

    manifest_path = bundle / "bundle_manifest.json"
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    gene_assay = dict(manifest["assays"][0])
    gene_assay.update(
        {
            "name": "log_expression",
            "path": "assays/log_expression.tsv.gz",
            "scale": "log2",
            "recommended_for": [
                "differential_expression",
                "dimension_reduction",
                "classifier",
                "signature_analysis",
                "deconvolution",
            ],
            "sha256": _sha256(log_path),
        }
    )
    manifest["assays"] = [
        gene_assay,
        {
            "name": "probe_expression",
            "path": "assays/probe_expression.tsv.gz",
            "value_type": "continuous",
            "scale": "log2",
            "feature_level": "probe",
            "recommended_for": [],
            "sha256": _sha256(probe_target),
        },
    ]
    manifest["qc"] = {
        "status": str(qc_summary["status"]),
        "metrics": "qc/array_qc_metrics.tsv",
        "sample_flags": "qc/sample_flags.tsv",
        "plots": [f"qc/plots/{plot.name}" for plot in sorted(plots_target.glob("*.svg"))],
    }
    manifest["microarray"] = {
        "platform_id": platform["platform_id"],
        "platform_definition_sha256": platform["definition_sha256"],
        "adapter_version": platform["adapter_version"],
        "normalization_engine": platform["normalization"]["engine"],
        "normalization_method": platform["normalization"]["method"],
        "rma_target": platform["normalization"]["target"],
        "annotation_package": platform["annotation"]["package"],
        "annotation_confidence": platform["annotation"]["confidence"],
        "aggregation_method": ingestion["aggregation_method"],
        "probe_expression_assay": "assays/probe_expression.tsv.gz",
        "probe_mapping": "mappings/probe_mapping.tsv",
    }
    write_json_atomic(manifest_path, manifest)
    schema = json.loads((ROOT / "schemas/expression_bundle.schema.json").read_text())
    Draft202012Validator(schema).validate(manifest)
    shutil.copyfile(manifest_path, output_dir / "bundle_manifest.json")
    summary_payload = summary.to_dict()
    summary_payload["value_types_available"] = ["log_expression", "probe_expression"]
    summary_payload["qc_status"] = qc_summary["status"]
    summary_payload["probe_count"] = qc_summary["probe_count"]
    summary_payload["platform_id"] = platform["platform_id"]
    write_json_atomic(output_dir / "bundle_summary.json", summary_payload)
    (output_dir / "expression_bundle.tar.gz").unlink(missing_ok=True)
    _archive_bundle(bundle, output_dir / "expression_bundle.tar.gz")


def _write_input_checksums(ingestion: dict[str, Any], target: Path) -> None:
    with target.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
        writer.writerow(("role", "path", "sha256"))
        metadata = ingestion["sample_metadata"]
        writer.writerow(("sample_metadata", metadata["original_name"], metadata["sha256"]))
        for sample in ingestion["samples"]:
            cel_file = sample["cel_file"]
            writer.writerow(("cel_file", cel_file["original_name"], cel_file["sha256"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ingestion-manifest", required=True, type=Path)
    parser.add_argument("--gene-expression", required=True, type=Path)
    parser.add_argument("--probe-expression", required=True, type=Path)
    parser.add_argument("--gene-feature-metadata", required=True, type=Path)
    parser.add_argument("--probe-mapping", required=True, type=Path)
    parser.add_argument("--array-qc-metrics", required=True, type=Path)
    parser.add_argument("--sample-flags", required=True, type=Path)
    parser.add_argument("--array-qc-summary", required=True, type=Path)
    parser.add_argument("--r-output-dir", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--prepared-dataset-id", required=True)
    parser.add_argument("--prepared-version", required=True, type=int)
    args = parser.parse_args(argv)
    build_microarray_bundle(
        args.ingestion_manifest,
        args.gene_expression,
        args.probe_expression,
        args.gene_feature_metadata,
        args.probe_mapping,
        args.array_qc_metrics,
        args.sample_flags,
        args.array_qc_summary,
        args.r_output_dir,
        args.metadata,
        args.output_dir,
        args.prepared_dataset_id,
        args.prepared_version,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
