"""Raw RNA-seq sample-sheet ingestion and pinned reference discovery."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path, PurePath
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api.models import Dataset, DatasetFile
from transcriptforge_api.schemas.datasets import RawRNASeqIngestionRequest
from transcriptforge_api.storage.base import StorageBackend

ROOT = Path(__file__).parents[4]
REFERENCE_ROOT = ROOT / "references" / "human"
SCHEMA_ROOT = ROOT / "schemas"
SAMPLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
LANE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
METADATA_COLUMN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
FASTQ_SUFFIX = re.compile(r".+\.(?:fastq|fq)(?:\.gz)?$", re.IGNORECASE)
MAX_SAMPLE_SHEET_BYTES = 5 * 1024 * 1024
MAX_SAMPLE_SHEET_ROWS = 10_000


class RawRNASeqIngestionError(ValueError):
    """Raised when uploaded FASTQ inputs cannot form one immutable ingestion manifest."""


def _load_schema(name: str) -> dict[str, Any]:
    return dict(json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8")))


def load_reference_bundle(reference_id: str) -> tuple[dict[str, Any], str]:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,127}", reference_id):
        raise RawRNASeqIngestionError("Reference bundle ID is unsafe.")
    path = REFERENCE_ROOT / f"{reference_id}.json"
    if not path.is_file():
        raise RawRNASeqIngestionError(f"Unknown reference bundle: {reference_id}.")
    payload_bytes = path.read_bytes()
    payload = dict(json.loads(payload_bytes))
    Draft202012Validator(_load_schema("reference_bundle.schema.json")).validate(payload)
    if payload["reference_id"] != reference_id:
        raise RawRNASeqIngestionError("Reference filename and embedded ID disagree.")
    return payload, hashlib.sha256(payload_bytes).hexdigest()


def list_reference_bundles() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in sorted(REFERENCE_ROOT.glob("*.json")):
        payload, digest = load_reference_bundle(path.stem)
        results.append(
            {
                "reference_id": payload["reference_id"],
                "definition_sha256": digest,
                "name": payload["name"],
                "organism": payload["organism"],
                "genome_build": payload["genome_build"],
                "annotation_provider": payload["annotation_provider"],
                "annotation_release": payload["annotation_release"],
                "salmon_version": payload["salmon"]["version"],
                "index_strategy": payload["salmon"]["index_strategy"],
                "source_page": payload["source_page"],
                "assets": payload["assets"],
            }
        )
    return results


async def build_ingestion_manifest(
    session: AsyncSession,
    storage: StorageBackend,
    dataset: Dataset,
    request: RawRNASeqIngestionRequest,
) -> dict[str, Any]:
    if dataset.modality != "bulk_rnaseq" or dataset.source_kind != "fastq":
        raise RawRNASeqIngestionError(
            "Raw RNA-seq ingestion requires a bulk_rnaseq dataset with source_kind fastq."
        )
    reference, reference_sha256 = load_reference_bundle(request.reference_bundle_id)
    if dataset.organism != reference["organism"]:
        raise RawRNASeqIngestionError("Dataset organism does not match the reference bundle.")
    if not (dataset.genome_build or "").startswith("GRCh38"):
        raise RawRNASeqIngestionError("The selected reference requires a GRCh38 dataset.")
    expected_annotation = f"GENCODE {reference['annotation_release']}"
    if dataset.annotation_release and dataset.annotation_release != expected_annotation:
        raise RawRNASeqIngestionError(
            f"Dataset annotation release must be '{expected_annotation}' for this reference."
        )

    files = list(
        await session.scalars(
            select(DatasetFile)
            .where(
                DatasetFile.dataset_id == dataset.id,
                DatasetFile.role.in_(("sample_sheet", "fastq_r1", "fastq_r2")),
            )
            .order_by(DatasetFile.created_at.desc(), DatasetFile.id.desc())
        )
    )
    sample_sheet = next((item for item in files if item.role == "sample_sheet"), None)
    if sample_sheet is None:
        raise RawRNASeqIngestionError("Upload a sample_sheet before raw RNA-seq ingestion.")
    if sample_sheet.size_bytes > MAX_SAMPLE_SHEET_BYTES:
        raise RawRNASeqIngestionError("Sample sheet exceeds the 5 MiB ingestion limit.")

    read_files: dict[tuple[str, str], DatasetFile] = {}
    for item in files:
        if item.role in {"fastq_r1", "fastq_r2"}:
            read_files.setdefault((item.role, item.original_name), item)
    rows, metadata_columns = _parse_sample_sheet(storage.read_bytes(sample_sheet.storage_uri))
    samples_by_id: dict[str, dict[str, Any]] = {}
    layouts: set[str] = set()
    used_file_ids: set[str] = set()
    used_read_names: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        sample_id = row["sample_id"]
        if not SAMPLE_ID.fullmatch(sample_id):
            raise RawRNASeqIngestionError(
                f"Row {row_number}: sample_id '{sample_id}' is unsafe or invalid."
            )
        lane_id = row.get("lane_id") or "lane_1"
        if not LANE_ID.fullmatch(lane_id):
            raise RawRNASeqIngestionError(
                f"Row {row_number}: lane_id '{lane_id}' is unsafe or invalid."
            )
        read1 = _resolve_read(read_files, "fastq_r1", row["read1"], row_number)
        read2_name = row["read2"]
        read2 = (
            _resolve_read(read_files, "fastq_r2", read2_name, row_number)
            if read2_name
            else None
        )
        layout = "paired_end" if read2 is not None else "single_end"
        layouts.add(layout)
        for assigned_read in (read1, read2):
            if assigned_read is None:
                continue
            if assigned_read.id in used_file_ids:
                raise RawRNASeqIngestionError(
                    f"Row {row_number}: FASTQ '{assigned_read.original_name}' "
                    "is assigned more than once."
                )
            used_file_ids.add(assigned_read.id)
            if assigned_read.original_name in used_read_names:
                raise RawRNASeqIngestionError(
                    f"Row {row_number}: FASTQ basename '{assigned_read.original_name}' "
                    "is not unique across the dataset."
                )
            used_read_names.add(assigned_read.original_name)
        metadata = {column: row[column] for column in metadata_columns}
        sample = samples_by_id.get(sample_id)
        if sample is None:
            sample = {"sample_id": sample_id, "lanes": [], "metadata": metadata}
            samples_by_id[sample_id] = sample
        elif sample["metadata"] != metadata:
            raise RawRNASeqIngestionError(
                f"Row {row_number}: metadata differs between lanes for sample '{sample_id}'."
            )
        if any(lane["lane_id"] == lane_id for lane in sample["lanes"]):
            raise RawRNASeqIngestionError(
                f"Row {row_number}: duplicate lane_id '{lane_id}' for sample '{sample_id}'."
            )
        sample["lanes"].append(
            {
                "lane_id": lane_id,
                "read1": _file_contract(read1),
                "read2": _file_contract(read2) if read2 is not None else None,
            }
        )
    if len(layouts) != 1:
        raise RawRNASeqIngestionError(
            "A sample sheet cannot mix single-end and paired-end libraries in one dataset."
        )
    warnings: list[str] = []
    uploaded_read_ids = {item.id for item in read_files.values()}
    unused_count = len(uploaded_read_ids - used_file_ids)
    if unused_count:
        warnings.append(
            f"{unused_count} uploaded FASTQ file(s) are not referenced by the active sample sheet."
        )
    samples = list(samples_by_id.values())
    manifest: dict[str, Any] = {
        "schema_version": "1.1.0",
        "dataset_id": dataset.id,
        "organism": dataset.organism,
        "genome_build": dataset.genome_build,
        "source_kind": "fastq",
        "reference": {
            "reference_id": reference["reference_id"],
            "definition_sha256": reference_sha256,
            "name": reference["name"],
            "annotation_release": expected_annotation,
            "salmon_version": reference["salmon"]["version"],
        },
        "sample_sheet": _file_contract(sample_sheet),
        "library_layout": next(iter(layouts)),
        "strandedness": request.strandedness,
        "sample_count": len(samples),
        "lane_count": len(rows),
        "read_file_count": len(used_file_ids),
        "samples": samples,
        "warnings": warnings,
    }
    Draft202012Validator(_load_schema("raw_rnaseq_ingestion.schema.json")).validate(manifest)
    return manifest


def _parse_sample_sheet(payload: bytes) -> tuple[list[dict[str, str]], list[str]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise RawRNASeqIngestionError("Sample sheet must be UTF-8 text.") from error
    if "\x00" in text:
        raise RawRNASeqIngestionError("Sample sheet contains NUL bytes.")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    headers = reader.fieldnames or []
    if len(headers) != len(set(headers)):
        raise RawRNASeqIngestionError("Sample sheet contains duplicate column names.")
    required = ["sample_id", "read1", "read2"]
    missing = [column for column in required if column not in headers]
    if missing:
        raise RawRNASeqIngestionError(
            "Sample sheet is missing required columns: " + ", ".join(missing) + "."
        )
    reserved = [*required, "lane_id"]
    metadata_columns = [column for column in headers if column not in reserved]
    invalid_metadata = [
        column for column in metadata_columns if not METADATA_COLUMN.fullmatch(column)
    ]
    if invalid_metadata:
        raise RawRNASeqIngestionError(
            "Sample metadata columns must use letters, digits, and underscores: "
            + ", ".join(invalid_metadata)
            + "."
        )
    rows: list[dict[str, str]] = []
    for row_number, raw in enumerate(reader, start=2):
        if None in raw:
            raise RawRNASeqIngestionError(f"Row {row_number} has more fields than the header.")
        row = {column: (raw.get(column) or "").strip() for column in headers}
        if not any(row.values()):
            continue
        if not row["sample_id"] or not row["read1"]:
            raise RawRNASeqIngestionError(
                f"Row {row_number} requires non-empty sample_id and read1 values."
            )
        rows.append(row)
        if len(rows) > MAX_SAMPLE_SHEET_ROWS:
            raise RawRNASeqIngestionError("Sample sheet exceeds the 10,000-lane-row limit.")
    if not rows:
        raise RawRNASeqIngestionError("Sample sheet does not contain any samples.")
    return rows, metadata_columns


def _resolve_read(
    files: dict[tuple[str, str], DatasetFile], role: str, name: str, row_number: int
) -> DatasetFile:
    if (
        PurePath(name).name != name
        or "/" in name
        or "\\" in name
        or not FASTQ_SUFFIX.fullmatch(name)
    ):
        raise RawRNASeqIngestionError(
            f"Row {row_number}: FASTQ names must be basenames ending in .fastq, .fq, or .gz."
        )
    item = files.get((role, name))
    if item is None:
        raise RawRNASeqIngestionError(
            f"Row {row_number}: '{name}' was not uploaded with role {role}."
        )
    if item.size_bytes < 1:
        raise RawRNASeqIngestionError(f"Row {row_number}: FASTQ '{name}' is empty.")
    return item


def _file_contract(item: DatasetFile) -> dict[str, Any]:
    return {
        "dataset_file_id": item.id,
        "role": item.role,
        "original_name": item.original_name,
        "storage_uri": item.storage_uri,
        "size_bytes": item.size_bytes,
        "sha256": item.sha256,
    }
