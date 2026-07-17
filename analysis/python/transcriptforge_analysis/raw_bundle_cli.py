"""Build a canonical Expression Bundle from tximport gene counts and TPM."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from transcriptforge_analysis.expression_bundle import (
    BundleConfig,
    _archive_bundle,
    build_expression_bundle,
)
from transcriptforge_analysis.matrix_validation import ValidationConfig, write_json_atomic


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


def build_raw_bundle(
    execution_path: Path,
    counts: Path,
    tpm: Path,
    transcript_tpm: Path,
    raw_qc_metrics: Path,
    raw_qc_summary: Path,
    metadata: Path,
    output_dir: Path,
    prepared_dataset_id: str,
    prepared_version: int,
) -> None:
    execution = dict(json.loads(execution_path.read_text(encoding="utf-8")))
    validation = ValidationConfig(
        dataset_id=str(execution["dataset_id"]),
        name="Raw RNA-seq quantification",
        matrix_path=counts,
        metadata_path=metadata,
        matrix_orientation="features_by_samples",
        feature_id_column="feature_id",
        sample_id_column="sample_id",
        value_type="raw_counts",
        modality="bulk_rnaseq",
        source_kind="fastq",
        organism=str(execution["organism"]),
        genome_build=str(execution["genome_build"]),
        annotation_release=str(execution["annotation_release"]),
        feature_id_type="ensembl_gene_id",
    )
    config = BundleConfig(
        validation=validation,
        prepared_dataset_id=prepared_dataset_id,
        prepared_version=prepared_version,
        strip_ensembl_version=True,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = build_expression_bundle(config, output_dir)
    bundle = output_dir / "expression_bundle"
    tpm_target = bundle / "assays/tpm.tsv.gz"
    _gzip_copy(tpm, tpm_target)
    transcript_target = bundle / "assays/transcript_abundance.tsv.gz"
    _gzip_copy(transcript_tpm, transcript_target)
    qc_metrics_target = bundle / "qc/raw_rnaseq_metrics.tsv"
    shutil.copyfile(raw_qc_metrics, qc_metrics_target)
    qc_summary_target = bundle / "qc/raw_rnaseq_summary.json"
    shutil.copyfile(raw_qc_summary, qc_summary_target)
    raw_qc = dict(json.loads(raw_qc_summary.read_text(encoding="utf-8")))

    manifest_path = bundle / "bundle_manifest.json"
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assays"].append(
        {
            "name": "tpm",
            "path": "assays/tpm.tsv.gz",
            "value_type": "nonnegative_continuous",
            "scale": "linear",
            "feature_level": "gene",
            "recommended_for": [
                "dimension_reduction",
                "classifier",
                "signature_analysis",
                "deconvolution",
            ],
            "sha256": _sha256(tpm_target),
        }
    )
    manifest["assays"].append(
        {
            "name": "transcript_abundance",
            "path": "assays/transcript_abundance.tsv.gz",
            "value_type": "nonnegative_continuous",
            "scale": "linear",
            "feature_level": "transcript",
            "recommended_for": [],
            "sha256": _sha256(transcript_target),
        }
    )
    manifest["quantification"] = {
        "method": "salmon_tximport",
        "counts_semantics": "rounded_estimated_counts",
        "tpm_assay": "assays/tpm.tsv.gz",
        "transcript_abundance_assay": "assays/transcript_abundance.tsv.gz",
    }
    generic_qc_status = str(manifest["qc"]["status"])
    raw_qc_status = str(raw_qc["status"])
    manifest["qc"]["status"] = (
        "SEVERE_REVIEW"
        if generic_qc_status == "SEVERE_REVIEW"
        else "REVIEW"
        if "REVIEW" in {generic_qc_status, raw_qc_status}
        else "PASS"
    )
    manifest["qc"]["raw_rnaseq_metrics"] = "qc/raw_rnaseq_metrics.tsv"
    manifest["qc"]["raw_rnaseq_summary"] = "qc/raw_rnaseq_summary.json"
    write_json_atomic(manifest_path, manifest)
    shutil.copyfile(manifest_path, output_dir / "bundle_manifest.json")
    summary_payload = summary.to_dict()
    summary_payload["value_types_available"] = ["raw_counts", "log_expression", "tpm"]
    summary_payload["qc_status"] = manifest["qc"]["status"]
    summary_payload["transcript_abundance_available"] = True
    write_json_atomic(output_dir / "bundle_summary.json", summary_payload)
    _archive_bundle(bundle, output_dir / "expression_bundle.tar.gz")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-manifest", required=True, type=Path)
    parser.add_argument("--counts", required=True, type=Path)
    parser.add_argument("--tpm", required=True, type=Path)
    parser.add_argument("--transcript-tpm", required=True, type=Path)
    parser.add_argument("--raw-qc-metrics", required=True, type=Path)
    parser.add_argument("--raw-qc-summary", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--prepared-dataset-id", required=True)
    parser.add_argument("--prepared-version", required=True, type=int)
    args = parser.parse_args(argv)
    build_raw_bundle(
        args.execution_manifest,
        args.counts,
        args.tpm,
        args.transcript_tpm,
        args.raw_qc_metrics,
        args.raw_qc_summary,
        args.metadata,
        args.output_dir,
        args.prepared_dataset_id,
        args.prepared_version,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
