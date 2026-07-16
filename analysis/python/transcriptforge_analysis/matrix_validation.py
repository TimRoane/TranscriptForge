"""Streaming expression-matrix and sample-metadata validation."""

import csv
import gzip
import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, TextIO, cast

Severity = Literal["ERROR", "WARNING"]
Orientation = Literal["features_by_samples", "samples_by_features"]
ValueType = Literal["raw_counts", "normalized_expression"]


@dataclass(frozen=True, slots=True)
class ValidationConfig:
    dataset_id: str
    name: str
    matrix_path: Path
    metadata_path: Path
    matrix_orientation: Orientation
    feature_id_column: str
    sample_id_column: str
    value_type: ValueType
    modality: str = "bulk_rnaseq"
    source_kind: str = "count_matrix"
    organism: str = "Homo sapiens"
    genome_build: str = "GRCh38"
    annotation_release: str = "GENCODE 49"
    feature_id_type: str = "ensembl_gene_id"

    @classmethod
    def from_json(cls, path: Path) -> "ValidationConfig":
        with path.open(encoding="utf-8") as source:
            payload = json.load(source)
        return cls(
            dataset_id=str(payload["dataset_id"]),
            name=str(payload["name"]),
            matrix_path=Path(payload["matrix_path"]),
            metadata_path=Path(payload["metadata_path"]),
            matrix_orientation=cast(Orientation, payload["matrix_orientation"]),
            feature_id_column=str(payload["feature_id_column"]),
            sample_id_column=str(payload["sample_id_column"]),
            value_type=cast(ValueType, payload["value_type"]),
            modality=str(payload.get("modality", "bulk_rnaseq")),
            source_kind=str(payload.get("source_kind", "count_matrix")),
            organism=str(payload.get("organism", "Homo sapiens")),
            genome_build=str(payload.get("genome_build", "GRCh38")),
            annotation_release=str(payload.get("annotation_release", "GENCODE 49")),
            feature_id_type=str(payload.get("feature_id_type", "ensembl_gene_id")),
        )


@dataclass(frozen=True, slots=True)
class Finding:
    severity: Severity
    code: str
    message: str
    location: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FindingCollector:
    limit: int = 100
    findings: list[Finding] = field(default_factory=list)
    suppressed: Counter[str] = field(default_factory=Counter)

    def add(
        self,
        severity: Severity,
        code: str,
        message: str,
        *,
        location: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if len(self.findings) < self.limit:
            self.findings.append(
                Finding(severity, code, message, location, details or {})
            )
        else:
            self.suppressed[code] += 1


@dataclass(frozen=True, slots=True)
class MatrixSummary:
    orientation: Orientation
    sample_count: int
    feature_count: int
    data_cell_count: int
    missing_cell_count: int
    non_numeric_cell_count: int
    negative_cell_count: int
    non_integer_cell_count: int
    duplicate_sample_count: int
    duplicate_feature_count: int


@dataclass(frozen=True, slots=True)
class MetadataSummary:
    sample_count: int
    column_count: int
    duplicate_sample_count: int
    missing_sample_id_count: int
    matrix_only_samples: tuple[str, ...]
    metadata_only_samples: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValidationReport:
    schema_version: str
    status: Literal["VALID", "INVALID"]
    matrix: MatrixSummary
    metadata: MetadataSummary
    findings: tuple[Finding, ...]
    suppressed_findings: dict[str, int]
    preview: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(json.dumps(asdict(self))))


@dataclass(slots=True)
class _MatrixState:
    sample_ids: list[str] = field(default_factory=list)
    feature_ids: list[str] = field(default_factory=list)
    feature_count: int = 0
    sample_count: int = 0
    data_cell_count: int = 0
    missing_cell_count: int = 0
    non_numeric_cell_count: int = 0
    negative_cell_count: int = 0
    non_integer_cell_count: int = 0
    duplicate_sample_count: int = 0
    duplicate_feature_count: int = 0
    preview_rows: list[dict[str, Any]] = field(default_factory=list)


def validate_dataset(config: ValidationConfig) -> ValidationReport:
    """Validate one matrix/metadata pair without materializing the numeric matrix."""
    findings = FindingCollector()
    matrix_state = _validate_matrix(config, findings)
    metadata_summary, metadata_preview = _validate_metadata(
        config, set(matrix_state.sample_ids), findings
    )
    matrix_summary = MatrixSummary(
        orientation=config.matrix_orientation,
        sample_count=matrix_state.sample_count,
        feature_count=matrix_state.feature_count,
        data_cell_count=matrix_state.data_cell_count,
        missing_cell_count=matrix_state.missing_cell_count,
        non_numeric_cell_count=matrix_state.non_numeric_cell_count,
        negative_cell_count=matrix_state.negative_cell_count,
        non_integer_cell_count=matrix_state.non_integer_cell_count,
        duplicate_sample_count=matrix_state.duplicate_sample_count,
        duplicate_feature_count=matrix_state.duplicate_feature_count,
    )
    status: Literal["VALID", "INVALID"] = (
        "INVALID" if any(item.severity == "ERROR" for item in findings.findings) else "VALID"
    )
    return ValidationReport(
        schema_version="1.0.0",
        status=status,
        matrix=matrix_summary,
        metadata=metadata_summary,
        findings=tuple(findings.findings),
        suppressed_findings=dict(findings.suppressed),
        preview={
            "matrix_columns": matrix_state.sample_ids[:10]
            if config.matrix_orientation == "features_by_samples"
            else matrix_state.feature_ids[:10],
            "matrix_rows": matrix_state.preview_rows,
            "metadata_rows": metadata_preview,
        },
    )


def build_dataset_manifest(config: ValidationConfig) -> dict[str, Any]:
    """Build the frozen source manifest after successful validation."""
    return {
        "schema_version": "1.0.0",
        "dataset_id": config.dataset_id,
        "name": config.name,
        "organism": config.organism,
        "modality": config.modality,
        "source_kind": config.source_kind,
        "genome_build": config.genome_build,
        "annotation_release": config.annotation_release,
        "feature_id_type": config.feature_id_type,
        "value_type": config.value_type,
        "matrix_orientation": config.matrix_orientation,
        "matrix_file": config.matrix_path.name,
        "sample_metadata_file": config.metadata_path.name,
        "sample_id_column": config.sample_id_column,
        "feature_id_column": config.feature_id_column,
        "paired_end": None,
        "strandedness": None,
        "created_by": "transcriptforge",
        "checksums": {
            config.matrix_path.name: _sha256(config.matrix_path),
            config.metadata_path.name: _sha256(config.metadata_path),
        },
    }


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON through a sibling temporary file and atomically publish it."""
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as destination:
        json.dump(payload, destination, indent=2, sort_keys=True)
        destination.write("\n")
        destination.flush()
    temporary.replace(path)


def _validate_matrix(config: ValidationConfig, findings: FindingCollector) -> _MatrixState:
    state = _MatrixState()
    seen_features: set[str] = set()
    seen_samples: set[str] = set()
    with _open_table(config.matrix_path) as source:
        reader = csv.reader(source, delimiter=_delimiter(config.matrix_path, source))
        header = next(reader, None)
        if not header:
            findings.add("ERROR", "MATRIX_EMPTY", "The expression matrix is empty.")
            return state
        duplicates = _duplicates(header)
        if duplicates:
            findings.add(
                "ERROR",
                "MATRIX_DUPLICATE_COLUMN",
                "The expression matrix header contains duplicate columns.",
                details={"columns": sorted(duplicates)[:20]},
            )

        id_column = (
            config.feature_id_column
            if config.matrix_orientation == "features_by_samples"
            else config.sample_id_column
        )
        if id_column not in header:
            findings.add(
                "ERROR",
                "MATRIX_ID_COLUMN_MISSING",
                f"Required matrix identifier column '{id_column}' was not found.",
            )
            return state
        id_index = header.index(id_column)
        value_columns = [value for index, value in enumerate(header) if index != id_index]

        if config.matrix_orientation == "features_by_samples":
            state.sample_ids = value_columns
            state.sample_count = len(value_columns)
            state.duplicate_sample_count = len(_duplicates(value_columns))
        else:
            state.feature_ids = value_columns
            state.feature_count = len(value_columns)
            state.duplicate_feature_count = len(_duplicates(value_columns))

        for line_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                findings.add(
                    "ERROR",
                    "MATRIX_ROW_WIDTH",
                    f"Matrix row {line_number} has {len(row)} fields; expected {len(header)}.",
                    location=f"matrix:{line_number}",
                )
                continue
            identifier = row[id_index].strip()
            if not identifier:
                findings.add(
                    "ERROR",
                    "MATRIX_BLANK_IDENTIFIER",
                    "A matrix row has a blank identifier.",
                    location=f"matrix:{line_number}",
                )
            if config.matrix_orientation == "features_by_samples":
                if identifier in seen_features:
                    state.duplicate_feature_count += 1
                    findings.add(
                        "ERROR",
                        "MATRIX_DUPLICATE_FEATURE",
                        f"Feature identifier '{identifier}' occurs more than once.",
                        location=f"matrix:{line_number}",
                    )
                seen_features.add(identifier)
                state.feature_count += 1
                if len(state.feature_ids) < 10:
                    state.feature_ids.append(identifier)
            else:
                if identifier in seen_samples:
                    state.duplicate_sample_count += 1
                    findings.add(
                        "ERROR",
                        "MATRIX_DUPLICATE_SAMPLE",
                        f"Sample identifier '{identifier}' occurs more than once.",
                        location=f"matrix:{line_number}",
                    )
                seen_samples.add(identifier)
                state.sample_ids.append(identifier)
                state.sample_count += 1

            preview_values: dict[str, str] = {}
            for index, value in enumerate(row):
                if index == id_index:
                    continue
                column = header[index]
                _validate_value(value.strip(), config, state, findings, line_number, column)
                if len(preview_values) < 5:
                    preview_values[column] = value
            if len(state.preview_rows) < 5:
                state.preview_rows.append({"id": identifier, "values": preview_values})
    return state


def _validate_value(
    value: str,
    config: ValidationConfig,
    state: _MatrixState,
    findings: FindingCollector,
    line_number: int,
    column: str,
) -> None:
    state.data_cell_count += 1
    if not value:
        state.missing_cell_count += 1
        findings.add(
            "ERROR",
            "MATRIX_MISSING_VALUE",
            "Expression matrices cannot contain missing values in version 1.",
            location=f"matrix:{line_number}:{column}",
        )
        return
    try:
        numeric = float(value)
    except ValueError:
        state.non_numeric_cell_count += 1
        findings.add(
            "ERROR",
            "MATRIX_NON_NUMERIC",
            f"Value '{value}' is not numeric.",
            location=f"matrix:{line_number}:{column}",
        )
        return
    if not math.isfinite(numeric):
        state.non_numeric_cell_count += 1
        findings.add(
            "ERROR",
            "MATRIX_NON_FINITE",
            "Expression values must be finite.",
            location=f"matrix:{line_number}:{column}",
        )
    if config.value_type == "raw_counts":
        if numeric < 0:
            state.negative_cell_count += 1
            findings.add(
                "ERROR",
                "COUNT_MATRIX_NEGATIVE",
                "Raw counts cannot be negative.",
                location=f"matrix:{line_number}:{column}",
            )
        if math.isfinite(numeric) and not numeric.is_integer():
            state.non_integer_cell_count += 1
            findings.add(
                "ERROR",
                "COUNT_MATRIX_NON_INTEGER",
                "Raw counts must be integer-like values.",
                location=f"matrix:{line_number}:{column}",
            )


def _validate_metadata(
    config: ValidationConfig,
    matrix_samples: set[str],
    findings: FindingCollector,
) -> tuple[MetadataSummary, list[dict[str, str]]]:
    sample_ids: list[str] = []
    preview: list[dict[str, str]] = []
    duplicate_count = 0
    missing_count = 0
    column_count = 0
    with _open_table(config.metadata_path) as source:
        reader = csv.DictReader(source, delimiter=_delimiter(config.metadata_path, source))
        if not reader.fieldnames:
            findings.add("ERROR", "METADATA_EMPTY", "The sample metadata file is empty.")
        elif config.sample_id_column not in reader.fieldnames:
            findings.add(
                "ERROR",
                "METADATA_SAMPLE_COLUMN_MISSING",
                f"Required metadata column '{config.sample_id_column}' was not found.",
            )
        else:
            column_count = len(reader.fieldnames)
            seen: set[str] = set()
            for line_number, row in enumerate(reader, start=2):
                sample_id = (row.get(config.sample_id_column) or "").strip()
                if not sample_id:
                    missing_count += 1
                    findings.add(
                        "ERROR",
                        "METADATA_BLANK_SAMPLE",
                        "A metadata row has a blank sample identifier.",
                        location=f"metadata:{line_number}",
                    )
                elif sample_id in seen:
                    duplicate_count += 1
                    findings.add(
                        "ERROR",
                        "METADATA_DUPLICATE_SAMPLE",
                        f"Sample identifier '{sample_id}' occurs more than once in metadata.",
                        location=f"metadata:{line_number}",
                    )
                else:
                    seen.add(sample_id)
                    sample_ids.append(sample_id)
                if len(preview) < 5:
                    preview.append({key: value or "" for key, value in row.items()})

    metadata_samples = set(sample_ids)
    matrix_only = tuple(sorted(matrix_samples - metadata_samples))
    metadata_only = tuple(sorted(metadata_samples - matrix_samples))
    if matrix_only or metadata_only:
        findings.add(
            "ERROR",
            "SAMPLE_ID_MISMATCH",
            "Matrix and metadata sample identifiers do not match exactly.",
            details={
                "matrix_only": list(matrix_only[:50]),
                "metadata_only": list(metadata_only[:50]),
            },
        )
    return (
        MetadataSummary(
            sample_count=len(sample_ids),
            column_count=column_count,
            duplicate_sample_count=duplicate_count,
            missing_sample_id_count=missing_count,
            matrix_only_samples=matrix_only,
            metadata_only_samples=metadata_only,
        ),
        preview,
    )


def _open_table(path: Path) -> TextIO:
    if path.suffix.lower() == ".gz":
        return gzip.open(path, mode="rt", encoding="utf-8-sig", newline="")
    return path.open(encoding="utf-8-sig", newline="")


def _delimiter(path: Path, source: TextIO) -> str:
    first_line = source.readline()
    source.seek(0)
    if "\t" in first_line:
        return "\t"
    if "," in first_line:
        return ","
    inner_suffix = (
        Path(path.stem).suffix.lower()
        if path.suffix.lower() == ".gz"
        else path.suffix.lower()
    )
    return "," if inner_suffix == ".csv" else "\t"


def _duplicates(values: list[str]) -> set[str]:
    return {value for value, count in Counter(values).items() if count > 1}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
