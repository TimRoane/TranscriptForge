"""Deterministic matrix and metadata validation tests."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from transcriptforge_analysis.cli import main
from transcriptforge_analysis.matrix_validation import (
    ValidationConfig,
    build_dataset_manifest,
    validate_dataset,
)

ROOT = Path(__file__).parents[3]


def config_for(matrix: Path, metadata: Path, **changes: object) -> ValidationConfig:
    values: dict[str, object] = {
        "dataset_id": "test-dataset",
        "name": "Test counts",
        "matrix_path": matrix,
        "metadata_path": metadata,
        "matrix_orientation": "features_by_samples",
        "feature_id_column": "gene_id",
        "sample_id_column": "sample_id",
        "value_type": "raw_counts",
    }
    values.update(changes)
    return ValidationConfig(**values)  # type: ignore[arg-type]


def test_valid_count_matrix_and_manifest() -> None:
    config = config_for(
        ROOT / "demo/data/counts.tsv", ROOT / "demo/metadata/sample_metadata.tsv"
    )
    report = validate_dataset(config)

    assert report.status == "VALID"
    assert report.matrix.sample_count == 4
    assert report.matrix.feature_count == 5
    assert report.matrix.data_cell_count == 20
    assert report.metadata.sample_count == 4
    assert report.findings == ()
    assert len(report.preview["matrix_rows"]) == 5

    report_schema = json.loads((ROOT / "schemas/validation_report.schema.json").read_text())
    Draft202012Validator(report_schema).validate(report.to_dict())

    manifest = build_dataset_manifest(config)
    schema = json.loads((ROOT / "schemas/dataset_manifest.schema.json").read_text())
    Draft202012Validator(schema).validate(manifest)
    assert len(manifest["checksums"]) == 2


def test_invalid_counts_produce_actionable_findings(tmp_path: Path) -> None:
    matrix = tmp_path / "counts.tsv"
    matrix.write_text(
        "gene_id\ts1\ts2\nENSG1\t1\t-2\nENSG1\t3.5\tbad\n",
        encoding="utf-8",
    )
    metadata = tmp_path / "metadata.tsv"
    metadata.write_text("sample_id\tgroup\ns1\ta\ns3\tb\n", encoding="utf-8")

    report = validate_dataset(config_for(matrix, metadata))
    codes = {finding.code for finding in report.findings}

    assert report.status == "INVALID"
    assert {
        "COUNT_MATRIX_NEGATIVE",
        "COUNT_MATRIX_NON_INTEGER",
        "MATRIX_NON_NUMERIC",
        "MATRIX_DUPLICATE_FEATURE",
        "SAMPLE_ID_MISMATCH",
    } <= codes
    mismatch = next(item for item in report.findings if item.code == "SAMPLE_ID_MISMATCH")
    assert mismatch.details == {"matrix_only": ["s2"], "metadata_only": ["s3"]}


def test_samples_by_features_orientation(tmp_path: Path) -> None:
    matrix = tmp_path / "counts.csv"
    matrix.write_text("sample_id,ENSG1,ENSG2\ns1,1,2\ns2,3,4\n", encoding="utf-8")
    metadata = tmp_path / "metadata.csv"
    metadata.write_text("sample_id,group\ns2,b\ns1,a\n", encoding="utf-8")

    report = validate_dataset(
        config_for(matrix, metadata, matrix_orientation="samples_by_features")
    )

    assert report.status == "VALID"
    assert report.matrix.sample_count == 2
    assert report.matrix.feature_count == 2


def test_cli_writes_report_and_manifest(tmp_path: Path) -> None:
    report_path = tmp_path / "validation_report.json"
    manifest_path = tmp_path / "dataset_manifest.json"

    exit_code = main(
        [
            "--config",
            str(ROOT / "demo/configs/count_matrix_validation.json"),
            "--matrix",
            str(ROOT / "demo/data/counts.tsv"),
            "--metadata",
            str(ROOT / "demo/metadata/sample_metadata.tsv"),
            "--output",
            str(report_path),
            "--manifest-output",
            str(manifest_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(report_path.read_text())["status"] == "VALID"
    assert json.loads(manifest_path.read_text())["dataset_id"] == "demo_airway_counts"
