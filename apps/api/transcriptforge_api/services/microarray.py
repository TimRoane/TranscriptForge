"""Affymetrix CEL platform registry and immutable ingestion validation."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
from pathlib import Path, PurePath
from tempfile import SpooledTemporaryFile
from typing import Any, BinaryIO, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api.models import Dataset, DatasetFile
from transcriptforge_api.schemas.datasets import MicroarrayIngestionRequest
from transcriptforge_api.storage.base import StorageBackend

ROOT = Path(__file__).parents[4]
PLATFORM_ROOT = ROOT / "microarray" / "platforms"
SCHEMA_ROOT = ROOT / "schemas"
SAMPLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
METADATA_COLUMN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
CEL_SUFFIX = re.compile(r".+\.cel(?:\.gz)?$", re.IGNORECASE)
MAX_METADATA_BYTES = 5 * 1024 * 1024
MAX_SAMPLES = 10_000
MAX_CEL_HEADER_BYTES = 1024 * 1024


class MicroarrayIngestionError(ValueError):
    """Raised when CEL inputs do not match one supported platform adapter."""


def _load_schema(name: str) -> dict[str, Any]:
    return dict(json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8")))


def load_platform_adapter(platform_id: str) -> tuple[dict[str, Any], str]:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,127}", platform_id):
        raise MicroarrayIngestionError("Microarray platform ID is unsafe.")
    path = PLATFORM_ROOT / f"{platform_id}.json"
    if not path.is_file():
        supported = ", ".join(item.stem for item in sorted(PLATFORM_ROOT.glob("*.json")))
        raise MicroarrayIngestionError(
            f"Unsupported Affymetrix platform '{platform_id}'. Supported platforms: {supported}."
        )
    payload_bytes = path.read_bytes()
    payload = dict(json.loads(payload_bytes))
    Draft202012Validator(_load_schema("microarray_platform.schema.json")).validate(payload)
    if payload["platform_id"] != platform_id:
        raise MicroarrayIngestionError("Platform adapter filename and embedded ID disagree.")
    return payload, hashlib.sha256(payload_bytes).hexdigest()


def list_platform_adapters() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in sorted(PLATFORM_ROOT.glob("*.json")):
        payload, digest = load_platform_adapter(path.stem)
        results.append({**payload, "definition_sha256": digest})
    return results


async def build_ingestion_manifest(
    session: AsyncSession,
    storage: StorageBackend,
    dataset: Dataset,
    request: MicroarrayIngestionRequest,
) -> dict[str, Any]:
    if dataset.modality != "microarray" or dataset.source_kind != "affymetrix_cel":
        raise MicroarrayIngestionError(
            "CEL ingestion requires a microarray dataset with source_kind affymetrix_cel."
        )
    platform, platform_sha256 = load_platform_adapter(request.platform_id)
    if dataset.organism != platform["organism"]:
        raise MicroarrayIngestionError("Dataset organism does not match the platform adapter.")
    supported_aggregation = set(platform["aggregation"]["supported_methods"])
    if request.aggregation_method not in supported_aggregation:
        raise MicroarrayIngestionError(
            f"Aggregation method '{request.aggregation_method}' is not supported by "
            f"platform '{request.platform_id}'."
        )

    files = list(
        await session.scalars(
            select(DatasetFile)
            .where(
                DatasetFile.dataset_id == dataset.id,
                DatasetFile.role.in_(("cel_file", "sample_metadata")),
            )
            .order_by(DatasetFile.created_at.desc(), DatasetFile.id.desc())
        )
    )
    metadata_file = next((item for item in files if item.role == "sample_metadata"), None)
    if metadata_file is None:
        raise MicroarrayIngestionError("Upload sample_metadata before CEL ingestion.")
    if metadata_file.size_bytes > MAX_METADATA_BYTES:
        raise MicroarrayIngestionError("Sample metadata exceeds the 5 MiB ingestion limit.")

    cel_files: dict[str, DatasetFile] = {}
    for item in files:
        if item.role != "cel_file":
            continue
        if not CEL_SUFFIX.fullmatch(item.original_name):
            raise MicroarrayIngestionError(
                f"CEL file '{item.original_name}' must end in .CEL or .CEL.gz."
            )
        cel_files.setdefault(item.original_name, item)
    if not cel_files:
        raise MicroarrayIngestionError("Upload at least one CEL file before ingestion.")

    rows, metadata_columns = _parse_sample_metadata(
        storage.read_bytes(metadata_file.storage_uri)
    )
    used_file_ids: set[str] = set()
    detected_formats: set[str] = set()
    detected_chip_types: set[str] = set()
    samples: list[dict[str, Any]] = []
    seen_sample_ids: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        sample_id = row["sample_id"]
        if not SAMPLE_ID.fullmatch(sample_id):
            raise MicroarrayIngestionError(
                f"Row {row_number}: sample_id '{sample_id}' is unsafe or invalid."
            )
        if sample_id in seen_sample_ids:
            raise MicroarrayIngestionError(
                f"Row {row_number}: duplicate sample_id '{sample_id}'."
            )
        seen_sample_ids.add(sample_id)
        cel_name = row["cel_file"]
        if PurePath(cel_name).name != cel_name or "/" in cel_name or "\\" in cel_name:
            raise MicroarrayIngestionError(
                f"Row {row_number}: CEL file references must be plain basenames."
            )
        cel_file = cel_files.get(cel_name)
        if cel_file is None:
            raise MicroarrayIngestionError(
                f"Row {row_number}: CEL file '{cel_name}' was not uploaded."
            )
        if cel_file.id in used_file_ids:
            raise MicroarrayIngestionError(
                f"Row {row_number}: CEL file '{cel_name}' is assigned more than once."
            )
        cel_format, chip_type = _inspect_cel(storage, cel_file, platform)
        detected_formats.add(cel_format)
        detected_chip_types.add(chip_type)
        used_file_ids.add(cel_file.id)
        samples.append(
            {
                "sample_id": sample_id,
                "cel_file": _file_contract(cel_file),
                "metadata": {column: row[column] for column in metadata_columns},
            }
        )
    if len(detected_formats) != 1:
        raise MicroarrayIngestionError(
            "A single microarray dataset cannot mix Calvin and XDA CEL formats."
        )
    if len(detected_chip_types) != 1:
        raise MicroarrayIngestionError(
            "CEL files resolve to more than one chip type; split them into separate datasets."
        )
    unused_count = len(cel_files) - len(used_file_ids)
    warnings = (
        [f"{unused_count} uploaded CEL file(s) are not referenced by sample metadata."]
        if unused_count
        else []
    )
    manifest: dict[str, Any] = {
        "schema_version": "1.0.0",
        "dataset_id": dataset.id,
        "organism": dataset.organism,
        "source_kind": "affymetrix_cel",
        "platform": {
            "platform_id": platform["platform_id"],
            "definition_sha256": platform_sha256,
            "adapter_version": platform["adapter_version"],
            "vendor": platform["vendor"],
            "array_design": platform["array_design"],
            "detected_chip_type": next(iter(detected_chip_types)),
            "cel_format": next(iter(detected_formats)),
            "normalization": platform["normalization"],
            "annotation": platform["annotation"],
        },
        "aggregation_method": request.aggregation_method,
        "sample_metadata": _file_contract(metadata_file),
        "sample_count": len(samples),
        "cel_file_count": len(used_file_ids),
        "samples": samples,
        "warnings": warnings,
    }
    Draft202012Validator(_load_schema("microarray_ingestion.schema.json")).validate(manifest)
    return manifest


def _parse_sample_metadata(payload: bytes) -> tuple[list[dict[str, str]], list[str]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise MicroarrayIngestionError("Sample metadata must be UTF-8 text.") from error
    if "\x00" in text:
        raise MicroarrayIngestionError("Sample metadata contains NUL bytes.")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    headers = reader.fieldnames or []
    if len(headers) != len(set(headers)):
        raise MicroarrayIngestionError("Sample metadata contains duplicate column names.")
    missing = [column for column in ("sample_id", "cel_file") if column not in headers]
    if missing:
        raise MicroarrayIngestionError(
            "Sample metadata is missing required columns: " + ", ".join(missing) + "."
        )
    metadata_columns = [column for column in headers if column not in {"sample_id", "cel_file"}]
    invalid_columns = [
        column for column in metadata_columns if not METADATA_COLUMN.fullmatch(column)
    ]
    if invalid_columns:
        raise MicroarrayIngestionError(
            "Sample metadata columns must use letters, digits, and underscores: "
            + ", ".join(invalid_columns)
            + "."
        )
    rows: list[dict[str, str]] = []
    for row_number, raw in enumerate(reader, start=2):
        if None in raw:
            raise MicroarrayIngestionError(
                f"Row {row_number} has more fields than the header."
            )
        row = {column: (raw.get(column) or "").strip() for column in headers}
        if not any(row.values()):
            continue
        if not row["sample_id"] or not row["cel_file"]:
            raise MicroarrayIngestionError(
                f"Row {row_number} requires non-empty sample_id and cel_file values."
            )
        rows.append(row)
        if len(rows) > MAX_SAMPLES:
            raise MicroarrayIngestionError("Sample metadata exceeds the 10,000-sample limit.")
    if not rows:
        raise MicroarrayIngestionError("Sample metadata does not contain any samples.")
    return rows, metadata_columns


def _inspect_cel(
    storage: StorageBackend, cel_file: DatasetFile, platform: dict[str, Any]
) -> tuple[str, str]:
    if cel_file.size_bytes < 4:
        raise MicroarrayIngestionError(
            f"CEL file '{cel_file.original_name}' is empty or truncated."
        )
    with SpooledTemporaryFile(max_size=8 * 1024 * 1024) as staged:
        staged_binary = cast(BinaryIO, staged)
        storage.download(cel_file.storage_uri, staged_binary)
        staged.seek(0)
        prefix = _read_cel_prefix(staged_binary, cel_file.original_name)
    if len(prefix) < 4:
        raise MicroarrayIngestionError(f"CEL file '{cel_file.original_name}' is truncated.")
    if prefix[0] == 59 and prefix[1] == 1:
        cel_format = "calvin"
    elif int.from_bytes(prefix[:4], byteorder="little", signed=False) == 64:
        cel_format = "xda"
    else:
        raise MicroarrayIngestionError(
            f"File '{cel_file.original_name}' is not a recognized Affymetrix Calvin "
            "or XDA CEL file."
        )
    aliases = [str(alias) for alias in platform["chip_type_aliases"]]
    detected = next((alias for alias in aliases if _contains_alias(prefix, alias)), None)
    if detected is None:
        expected = ", ".join(aliases)
        raise MicroarrayIngestionError(
            f"Unsupported array in CEL file '{cel_file.original_name}'. Expected chip type: "
            f"{expected}. Select a matching platform adapter or upload a supported array."
        )
    return cel_format, detected


def _read_cel_prefix(source: BinaryIO, original_name: str) -> bytes:
    try:
        if original_name.lower().endswith(".gz"):
            with gzip.GzipFile(fileobj=source, mode="rb") as uncompressed:
                return uncompressed.read(MAX_CEL_HEADER_BYTES)
        return source.read(MAX_CEL_HEADER_BYTES)
    except (OSError, EOFError) as error:
        raise MicroarrayIngestionError(
            f"CEL file '{original_name}' has invalid gzip compression."
        ) from error


def _contains_alias(payload: bytes, alias: str) -> bool:
    return any(
        encoding in payload
        for encoding in (alias.encode(), alias.encode("utf-16-be"), alias.encode("utf-16-le"))
    )


def _file_contract(item: DatasetFile) -> dict[str, Any]:
    return {
        "dataset_file_id": item.id,
        "role": item.role,
        "original_name": item.original_name,
        "storage_uri": item.storage_uri,
        "size_bytes": item.size_bytes,
        "sha256": item.sha256,
    }
