"""Canonical Expression Bundle construction for validated matrix datasets."""

import csv
import gzip
import hashlib
import json
import math
import mmap
import platform
import shutil
import struct
import tarfile
import tempfile
from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TextIO

from transcriptforge_analysis.matrix_validation import ValidationConfig, write_json_atomic

FEATURE_COLUMNS = (
    "feature_id",
    "ensembl_gene_id",
    "gene_symbol",
    "entrez_id",
    "gene_name",
    "gene_biotype",
    "chromosome",
    "start",
    "end",
    "mapping_status",
    "original_feature_id",
)


@dataclass(frozen=True, slots=True)
class BundleConfig:
    validation: ValidationConfig
    prepared_dataset_id: str
    prepared_version: int
    strip_ensembl_version: bool = False

    @classmethod
    def from_json(cls, path: Path) -> "BundleConfig":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            validation=ValidationConfig.from_json(path),
            prepared_dataset_id=str(payload["prepared_dataset_id"]),
            prepared_version=int(payload["prepared_version"]),
            strip_ensembl_version=bool(payload.get("strip_ensembl_version", False)),
        )


@dataclass(frozen=True, slots=True)
class MappingRecord:
    original_feature_id: str
    feature_id: str
    mapping_status: str


@dataclass(frozen=True, slots=True)
class BundleSummary:
    schema_version: str
    prepared_dataset_id: str
    prepared_version: int
    sample_count: int
    feature_count: int
    value_types_available: tuple[str, ...]
    qc_status: str
    mapped_feature_count: int
    unmapped_feature_count: int
    duplicate_group_count: int
    mapping_coverage: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_expression_bundle(config: BundleConfig, output_dir: Path) -> BundleSummary:
    """Build one immutable bundle from an already validated matrix/metadata pair."""
    bundle = output_dir / "expression_bundle"
    assays_dir = bundle / "assays"
    qc_dir = bundle / "qc"
    mappings_dir = bundle / "mappings"
    provenance_dir = bundle / "provenance"
    preview_dir = bundle / "preview"
    plots_dir = qc_dir / "plots"
    for directory in (
        assays_dir,
        qc_dir,
        mappings_dir,
        provenance_dir,
        preview_dir,
        plots_dir,
    ):
        directory.mkdir(parents=True, exist_ok=False)

    validation = config.validation
    sample_ids, original_features = _matrix_axes(validation)
    mappings = [
        _map_feature(value, validation.feature_id_type, config.strip_ensembl_version)
        for value in original_features
    ]
    groups: OrderedDict[str, list[MappingRecord]] = OrderedDict()
    for record in mappings:
        groups.setdefault(record.feature_id, []).append(record)

    assay_name = "raw_counts" if validation.value_type == "raw_counts" else "normalized_expression"
    assay_path = assays_dir / f"{assay_name}.tsv.gz"
    library_sizes = [0.0] * len(sample_ids)
    detected_features = [0] * len(sample_ids)
    if validation.matrix_orientation == "features_by_samples":
        _write_features_by_samples(
            validation,
            sample_ids,
            mappings,
            groups,
            assay_path,
            library_sizes,
            detected_features,
        )
    else:
        _write_samples_by_features(
            validation,
            sample_ids,
            mappings,
            groups,
            assay_path,
            library_sizes,
            detected_features,
        )

    sample_metadata = bundle / "sample_metadata.tsv"
    metadata_preview = _write_sample_metadata(validation, sample_ids, sample_metadata)
    feature_metadata = bundle / "feature_metadata.tsv"
    _write_mapping_outputs(groups, mappings, feature_metadata, mappings_dir)

    assays = [_assay_declaration(assay_name, assay_path, bundle)]
    value_types = [assay_name]
    if validation.value_type == "raw_counts":
        log_path = assays_dir / "log_expression.tsv.gz"
        _write_log_cpm(assay_path, log_path, library_sizes)
        assays.append(_assay_declaration("log_expression", log_path, bundle))
        value_types.append("log_expression")

    qc_status, qc_rows, flags = _write_qc(
        sample_ids,
        len(groups),
        library_sizes,
        detected_features,
        qc_dir,
        plots_dir,
    )
    mapped_count = sum(record.mapping_status != "unmapped" for record in mappings)
    unmapped_count = len(mappings) - mapped_count
    duplicate_groups = sum(len(records) > 1 for records in groups.values())
    coverage = mapped_count / len(mappings) if mappings else 0.0
    summary = BundleSummary(
        schema_version="1.0.0",
        prepared_dataset_id=config.prepared_dataset_id,
        prepared_version=config.prepared_version,
        sample_count=len(sample_ids),
        feature_count=len(groups),
        value_types_available=tuple(value_types),
        qc_status=qc_status,
        mapped_feature_count=mapped_count,
        unmapped_feature_count=unmapped_count,
        duplicate_group_count=duplicate_groups,
        mapping_coverage=coverage,
    )

    parameters_path = provenance_dir / "parameters.json"
    write_json_atomic(
        parameters_path,
        {
            "prepared_version": config.prepared_version,
            "matrix_orientation": validation.matrix_orientation,
            "feature_id_column": validation.feature_id_column,
            "sample_id_column": validation.sample_id_column,
            "feature_id_type": validation.feature_id_type,
            "strip_ensembl_version": config.strip_ensembl_version,
        },
    )
    checksums_path = provenance_dir / "input_checksums.tsv"
    _write_tsv(
        checksums_path,
        ("role", "path", "sha256"),
        (
            ("matrix", validation.matrix_path.name, _sha256(validation.matrix_path)),
            ("sample_metadata", validation.metadata_path.name, _sha256(validation.metadata_path)),
        ),
    )
    versions_path = provenance_dir / "software_versions.yml"
    versions_path.write_text(
        f"transcriptforge_analysis: 0.1.0\npython: {platform.python_version()}\n",
        encoding="utf-8",
    )
    (provenance_dir / "session_info.txt").write_text(platform.platform() + "\n", encoding="utf-8")

    write_json_atomic(preview_dir / "samples.json", {"rows": metadata_preview})
    write_json_atomic(
        preview_dir / "features.json",
        {
            "rows": [
                {
                    "feature_id": feature_id,
                    "mapping_status": records[0].mapping_status,
                    "original_feature_ids": [record.original_feature_id for record in records],
                }
                for feature_id, records in list(groups.items())[:20]
            ]
        },
    )
    write_json_atomic(
        preview_dir / "available_analyses.json",
        {
            "analyses": [
                "dimension_reduction",
                "classifier",
                "signature_analysis",
                "differential_expression",
            ]
        },
    )
    write_json_atomic(
        output_dir / "qc_summary.json",
        {"status": qc_status, "samples": qc_rows, "flags": flags},
    )
    write_json_atomic(output_dir / "feature_mapping_summary.json", summary.to_dict())

    manifest = {
        "schema_version": "1.0.0",
        "dataset_id": validation.dataset_id,
        "prepared_dataset_id": config.prepared_dataset_id,
        "organism": validation.organism,
        "genome_build": validation.genome_build,
        "annotation_release": validation.annotation_release,
        "primary_feature_id": "ensembl_gene_id",
        "sample_count": len(sample_ids),
        "feature_count": len(groups),
        "sample_metadata": "sample_metadata.tsv",
        "feature_metadata": "feature_metadata.tsv",
        "assays": assays,
        "qc": {
            "status": qc_status,
            "metrics": "qc/qc_metrics.tsv",
            "sample_flags": "qc/sample_flags.tsv",
        },
        "provenance": {
            "parameters": "provenance/parameters.json",
            "input_checksums": "provenance/input_checksums.tsv",
            "software_versions": "provenance/software_versions.yml",
        },
    }
    write_json_atomic(bundle / "bundle_manifest.json", manifest)
    shutil.copyfile(bundle / "bundle_manifest.json", output_dir / "bundle_manifest.json")
    write_json_atomic(output_dir / "bundle_summary.json", summary.to_dict())
    _archive_bundle(bundle, output_dir / "expression_bundle.tar.gz")
    return summary


def _matrix_axes(config: ValidationConfig) -> tuple[list[str], list[str]]:
    features: list[str] = []
    samples: list[str] = []
    with _open_table(config.matrix_path) as source:
        reader = csv.reader(source, delimiter=_delimiter(config.matrix_path, source))
        header = next(reader)
        if config.matrix_orientation == "features_by_samples":
            id_index = header.index(config.feature_id_column)
            samples = [value for index, value in enumerate(header) if index != id_index]
            features = [row[id_index].strip() for row in reader]
        else:
            id_index = header.index(config.sample_id_column)
            features = [value for index, value in enumerate(header) if index != id_index]
            samples = [row[id_index].strip() for row in reader]
    return samples, features


def _map_feature(feature_id: str, feature_id_type: str, strip_version: bool) -> MappingRecord:
    if feature_id_type == "ensembl_gene_id":
        if feature_id.startswith("ENSG") and feature_id[4:].isdigit() and len(feature_id) == 15:
            return MappingRecord(feature_id, feature_id, "mapped_identity")
        base, separator, version = feature_id.partition(".")
        if (
            strip_version
            and separator
            and version.isdigit()
            and base.startswith("ENSG")
            and base[4:].isdigit()
            and len(base) == 15
        ):
            return MappingRecord(feature_id, base, "mapped_version_stripped")
    return MappingRecord(feature_id, feature_id, "unmapped")


def _write_features_by_samples(
    config: ValidationConfig,
    sample_ids: list[str],
    mappings: list[MappingRecord],
    groups: OrderedDict[str, list[MappingRecord]],
    target: Path,
    library_sizes: list[float],
    detected_features: list[int],
) -> None:
    duplicate_values: dict[str, list[float]] = {
        feature_id: [0.0] * len(sample_ids)
        for feature_id, records in groups.items()
        if len(records) > 1
    }
    with _open_table(config.matrix_path) as source, gzip.open(
        target, "wt", encoding="utf-8", newline=""
    ) as destination:
        reader = csv.reader(source, delimiter=_delimiter(config.matrix_path, source))
        writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
        header = next(reader)
        id_index = header.index(config.feature_id_column)
        writer.writerow(["feature_id", *sample_ids])
        for row, mapping in zip(reader, mappings, strict=True):
            values = [_numeric(value) for index, value in enumerate(row) if index != id_index]
            if mapping.feature_id in duplicate_values:
                aggregate = duplicate_values[mapping.feature_id]
                for index, value in enumerate(values):
                    aggregate[index] += value
            else:
                writer.writerow([mapping.feature_id, *(_format_values(values, config.value_type))])
                _add_qc(values, library_sizes, detected_features)
        for feature_id, values in duplicate_values.items():
            writer.writerow([feature_id, *(_format_values(values, config.value_type))])
            _add_qc(values, library_sizes, detected_features)


def _write_samples_by_features(
    config: ValidationConfig,
    sample_ids: list[str],
    mappings: list[MappingRecord],
    groups: OrderedDict[str, list[MappingRecord]],
    target: Path,
    library_sizes: list[float],
    detected_features: list[int],
) -> None:
    feature_indices: dict[str, list[int]] = {}
    for index, mapping in enumerate(mappings):
        feature_indices.setdefault(mapping.feature_id, []).append(index)
    with tempfile.TemporaryFile() as binary:
        with _open_table(config.matrix_path) as source:
            reader = csv.reader(source, delimiter=_delimiter(config.matrix_path, source))
            header = next(reader)
            id_index = header.index(config.sample_id_column)
            for row in reader:
                values = [_numeric(value) for index, value in enumerate(row) if index != id_index]
                binary.write(struct.pack(f"<{len(values)}d", *values))
        binary.flush()
        with mmap.mmap(binary.fileno(), 0, access=mmap.ACCESS_READ) as matrix, gzip.open(
            target, "wt", encoding="utf-8", newline=""
        ) as destination:
            writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
            writer.writerow(["feature_id", *sample_ids])
            feature_count = len(mappings)
            for feature_id in groups:
                indices = feature_indices[feature_id]
                values = []
                for sample_index in range(len(sample_ids)):
                    offset = sample_index * feature_count * 8
                    values.append(
                        sum(
                            struct.unpack_from("<d", matrix, offset + index * 8)[0]
                            for index in indices
                        )
                    )
                writer.writerow([feature_id, *(_format_values(values, config.value_type))])
                _add_qc(values, library_sizes, detected_features)


def _write_sample_metadata(
    config: ValidationConfig, sample_ids: list[str], target: Path
) -> list[dict[str, str]]:
    with _open_table(config.metadata_path) as source:
        reader = csv.DictReader(source, delimiter=_delimiter(config.metadata_path, source))
        fieldnames = reader.fieldnames or []
        rows = {str(row[config.sample_id_column]): row for row in reader}
    ordered_fields = [
        "sample_id",
        *[value for value in fieldnames if value != config.sample_id_column],
    ]
    preview: list[dict[str, str]] = []
    with target.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(
            destination,
            fieldnames=ordered_fields,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for sample_id in sample_ids:
            source_row = rows[sample_id]
            row = {"sample_id": sample_id}
            row.update(
                {
                    field: str(source_row.get(field) or "")
                    for field in ordered_fields
                    if field != "sample_id"
                }
            )
            writer.writerow(row)
            if len(preview) < 20:
                preview.append(row)
    return preview


def _write_mapping_outputs(
    groups: OrderedDict[str, list[MappingRecord]],
    mappings: list[MappingRecord],
    feature_metadata: Path,
    mappings_dir: Path,
) -> None:
    _write_tsv(
        mappings_dir / "feature_mapping.tsv",
        ("original_feature_id", "feature_id", "mapping_status"),
        ((item.original_feature_id, item.feature_id, item.mapping_status) for item in mappings),
    )
    _write_tsv(
        mappings_dir / "unmapped_features.tsv",
        ("original_feature_id", "reason"),
        (
            (item.original_feature_id, "No explicit mapping was available")
            for item in mappings
            if item.mapping_status == "unmapped"
        ),
    )
    _write_tsv(
        mappings_dir / "duplicate_resolution.tsv",
        ("feature_id", "original_feature_ids", "resolution", "input_feature_count"),
        (
            (
                feature_id,
                ";".join(item.original_feature_id for item in records),
                "sum",
                len(records),
            )
            for feature_id, records in groups.items()
            if len(records) > 1
        ),
    )
    rows = []
    for feature_id, records in groups.items():
        status = records[0].mapping_status if len(records) == 1 else "duplicate_aggregated_sum"
        ensembl = feature_id if feature_id.startswith("ENSG") and len(feature_id) == 15 else ""
        rows.append(
            (
                feature_id,
                ensembl,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                status,
                ";".join(item.original_feature_id for item in records),
            )
        )
    _write_tsv(feature_metadata, FEATURE_COLUMNS, rows)


def _write_log_cpm(source_path: Path, target: Path, library_sizes: list[float]) -> None:
    with gzip.open(source_path, "rt", encoding="utf-8", newline="") as source, gzip.open(
        target, "wt", encoding="utf-8", newline=""
    ) as destination:
        reader = csv.reader(source, delimiter="\t")
        writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
        writer.writerow(next(reader))
        for row in reader:
            values = [float(value) for value in row[1:]]
            transformed = [
                math.log2((value / total * 1_000_000) + 1) if total > 0 else 0.0
                for value, total in zip(values, library_sizes, strict=True)
            ]
            writer.writerow([row[0], *(f"{value:.8g}" for value in transformed)])


def _write_qc(
    sample_ids: list[str],
    feature_count: int,
    library_sizes: list[float],
    detected_features: list[int],
    qc_dir: Path,
    plots_dir: Path,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    median_library = _median(library_sizes)
    median_detected = _median([float(value) for value in detected_features])
    rows: list[dict[str, Any]] = []
    flags: list[dict[str, Any]] = []
    for sample_id, library_size, detected in zip(
        sample_ids, library_sizes, detected_features, strict=True
    ):
        reasons = []
        if median_library > 0 and library_size < median_library * 0.2:
            reasons.append("LOW_LIBRARY_SIZE")
        if median_detected > 0 and detected < median_detected * 0.5:
            reasons.append("LOW_DETECTED_FEATURES")
        rows.append(
            {
                "sample_id": sample_id,
                "library_size": round(library_size, 8),
                "detected_features": detected,
                "detected_fraction": round(detected / feature_count, 8),
                "zero_fraction": round(1 - detected / feature_count, 8),
            }
        )
        flags.append(
            {
                "sample_id": sample_id,
                "status": "REVIEW" if reasons else "PASS",
                "reasons": reasons,
            }
        )
    status = "REVIEW" if any(item["status"] == "REVIEW" for item in flags) else "PASS"
    _write_tsv(
        qc_dir / "qc_metrics.tsv",
        ("sample_id", "library_size", "detected_features", "detected_fraction", "zero_fraction"),
        (
            (
                row["sample_id"],
                row["library_size"],
                row["detected_features"],
                row["detected_fraction"],
                row["zero_fraction"],
            )
            for row in rows
        ),
    )
    _write_tsv(
        qc_dir / "sample_flags.tsv",
        ("sample_id", "status", "reasons"),
        ((item["sample_id"], item["status"], ";".join(item["reasons"])) for item in flags),
    )
    _write_library_svg(sample_ids, library_sizes, plots_dir / "library_sizes.svg")
    return status, rows, flags


def _write_library_svg(sample_ids: list[str], values: list[float], target: Path) -> None:
    width = 720
    row_height = 32
    height = 50 + row_height * len(sample_ids)
    maximum = max(values, default=1.0) or 1.0
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
        ),
        '<rect width="100%" height="100%" fill="white"/>',
        (
            '<text x="16" y="24" font-family="sans-serif" font-size="16" '
            'font-weight="bold">Library size by sample</text>'
        ),
    ]
    for index, (sample_id, value) in enumerate(zip(sample_ids, values, strict=True)):
        y = 42 + index * row_height
        bar_width = int(480 * value / maximum)
        parts.extend(
            [
                (
                    f'<text x="16" y="{y + 16}" font-family="sans-serif" '
                    f'font-size="12">{_xml(sample_id)}</text>'
                ),
                f'<rect x="170" y="{y}" width="{bar_width}" height="20" rx="3" fill="#2563eb"/>',
                (
                    f'<text x="{180 + bar_width}" y="{y + 15}" '
                    f'font-family="sans-serif" font-size="11">{value:.6g}</text>'
                ),
            ]
        )
    parts.append("</svg>\n")
    target.write_text("".join(parts), encoding="utf-8")


def _assay_declaration(name: str, path: Path, bundle: Path) -> dict[str, Any]:
    if name == "raw_counts":
        return {
            "name": name,
            "path": path.relative_to(bundle).as_posix(),
            "value_type": "nonnegative_integer",
            "scale": "linear",
            "feature_level": "gene",
            "recommended_for": ["differential_expression"],
            "sha256": _sha256(path),
        }
    return {
        "name": name,
        "path": path.relative_to(bundle).as_posix(),
        "value_type": "continuous",
        "scale": "log2" if name == "log_expression" else "linear",
        "feature_level": "gene",
        "recommended_for": [
            "dimension_reduction",
            "classifier",
            "signature_analysis",
            "deconvolution",
        ],
        "sha256": _sha256(path),
    }


def _archive_bundle(bundle: Path, target: Path) -> None:
    with tarfile.open(target, "w:gz") as archive:
        archive.add(bundle, arcname="expression_bundle", recursive=True)


def _write_tsv(path: Path, header: tuple[str, ...], rows: Any) -> None:
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _add_qc(values: list[float], totals: list[float], detected: list[int]) -> None:
    for index, value in enumerate(values):
        totals[index] += value
        if value > 0:
            detected[index] += 1


def _format_values(values: list[float], value_type: str) -> Iterator[str]:
    for value in values:
        yield str(int(value)) if value_type == "raw_counts" else f"{value:.12g}"


def _numeric(value: str) -> float:
    return float(value.strip())


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if not ordered:
        return 0.0
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _open_table(path: Path) -> TextIO:
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open(encoding="utf-8-sig", newline="")


def _delimiter(path: Path, source: TextIO) -> str:
    first_line = source.readline()
    source.seek(0)
    if "\t" in first_line:
        return "\t"
    return "," if "," in first_line or path.suffix.lower() == ".csv" else "\t"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _xml(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
