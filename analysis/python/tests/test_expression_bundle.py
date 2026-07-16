"""Canonical Expression Bundle construction tests."""

import csv
import gzip
import json
import tarfile
from pathlib import Path

from jsonschema import Draft202012Validator
from transcriptforge_analysis.expression_bundle import BundleConfig, build_expression_bundle
from transcriptforge_analysis.matrix_validation import ValidationConfig

ROOT = Path(__file__).resolve().parents[3]


def _demo_config() -> BundleConfig:
    return BundleConfig(
        validation=ValidationConfig.from_json(
            ROOT / "demo/configs/count_matrix_validation.json"
        ),
        prepared_dataset_id="prepared-demo-1",
        prepared_version=1,
    )


def test_build_count_matrix_bundle_is_schema_valid_and_preserves_counts(
    tmp_path: Path,
) -> None:
    summary = build_expression_bundle(_demo_config(), tmp_path)
    bundle = tmp_path / "expression_bundle"
    manifest = json.loads((bundle / "bundle_manifest.json").read_text(encoding="utf-8"))
    schema = json.loads(
        (ROOT / "schemas/expression_bundle.schema.json").read_text(encoding="utf-8")
    )

    Draft202012Validator(schema).validate(manifest)
    assert summary.sample_count == 4
    assert summary.feature_count == 5
    assert summary.mapping_coverage == 1.0
    assert summary.qc_status == "PASS"
    assert [assay["name"] for assay in manifest["assays"]] == [
        "raw_counts",
        "log_expression",
    ]

    with (ROOT / "demo/data/counts.tsv").open(encoding="utf-8") as source:
        original = list(csv.reader(source, delimiter="\t"))
    with gzip.open(bundle / "assays/raw_counts.tsv.gz", "rt", encoding="utf-8") as source:
        canonical = list(csv.reader(source, delimiter="\t"))
    assert canonical == [["feature_id", *original[0][1:]], *original[1:]]
    assert (bundle / "qc/plots/library_sizes.svg").is_file()
    assert (tmp_path / "qc_summary.json").is_file()
    assert (tmp_path / "feature_mapping_summary.json").is_file()
    with tarfile.open(tmp_path / "expression_bundle.tar.gz", "r:gz") as archive:
        assert "expression_bundle/bundle_manifest.json" in archive.getnames()


def test_samples_by_features_transposes_and_sums_version_collisions(
    tmp_path: Path,
) -> None:
    matrix = tmp_path / "matrix.tsv"
    matrix.write_text(
        "sample_id\tENSG00000141510.1\tENSG00000141510.2\tENSG00000146648\n"
        "sample_A\t1\t2\t4\n"
        "sample_B\t3\t4\t5\n",
        encoding="utf-8",
    )
    metadata = tmp_path / "metadata.tsv"
    metadata.write_text(
        "sample_id\tcondition\nsample_B\ttreated\nsample_A\tcontrol\n",
        encoding="utf-8",
    )
    config = BundleConfig(
        validation=ValidationConfig(
            dataset_id="dataset-transposed",
            name="Transposed matrix",
            matrix_path=matrix,
            metadata_path=metadata,
            matrix_orientation="samples_by_features",
            feature_id_column="gene_id",
            sample_id_column="sample_id",
            value_type="raw_counts",
            feature_id_type="ensembl_gene_id",
        ),
        prepared_dataset_id="prepared-transposed-1",
        prepared_version=1,
        strip_ensembl_version=True,
    )
    output = tmp_path / "output"

    summary = build_expression_bundle(config, output)

    assert summary.feature_count == 2
    assert summary.duplicate_group_count == 1
    with gzip.open(
        output / "expression_bundle/assays/raw_counts.tsv.gz", "rt", encoding="utf-8"
    ) as source:
        rows = list(csv.reader(source, delimiter="\t"))
    assert rows == [
        ["feature_id", "sample_A", "sample_B"],
        ["ENSG00000141510", "3", "7"],
        ["ENSG00000146648", "4", "5"],
    ]
    duplicate_report = (
        output / "expression_bundle/mappings/duplicate_resolution.tsv"
    ).read_text(encoding="utf-8")
    assert "mapped" not in duplicate_report
    assert "ENSG00000141510.1;ENSG00000141510.2\tsum\t2" in duplicate_report
