"""Parse immutable signature definitions and map them to Expression Bundles."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import tarfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api.models import PreparedDataset, SignatureDefinition

MAX_SOURCE_BYTES = 5 * 1024 * 1024
MAX_ENTRIES = 50_000
MAX_SETS = 1_000
SAFE_IDENTIFIER = re.compile(r"^[^\x00-\x1f\x7f]{1,200}$")
ROOT = Path(__file__).parents[4]


class SignatureDefinitionError(ValueError):
    """Raised for unsafe or scientifically ambiguous signature input."""


def validate_document(document: dict[str, Any]) -> None:
    schema = json.loads((ROOT / "schemas/signature_definition.schema.json").read_text())
    Draft202012Validator(schema).validate(document)


def validate_mapping_report(document: dict[str, Any]) -> None:
    schema = json.loads((ROOT / "schemas/signature_mapping.schema.json").read_text())
    Draft202012Validator(schema).validate(document)


def parse_definition(
    payload: bytes,
    *,
    definition_id: str,
    name: str,
    description: str | None,
    definition_format: str,
    identifier_type: str,
) -> dict[str, Any]:
    if not payload or len(payload) > MAX_SOURCE_BYTES:
        raise SignatureDefinitionError("Signature files must contain 1 byte to 5 MiB.")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise SignatureDefinitionError("Signature files must be UTF-8 text.") from error
    if "\x00" in text:
        raise SignatureDefinitionError("Signature files cannot contain NUL bytes.")
    if definition_format == "gene_list":
        sets = [_parse_gene_list(text, definition_id, name, description)]
    elif definition_format == "gmt":
        sets = _parse_gmt(text)
    else:
        raise SignatureDefinitionError("Definition format must be gene_list or gmt.")
    if len(sets) > MAX_SETS:
        raise SignatureDefinitionError(f"GMT files cannot contain more than {MAX_SETS} sets.")
    total_unique = sum(len(item["entries"]) for item in sets)
    if total_unique > MAX_ENTRIES:
        raise SignatureDefinitionError(
            f"Signature definitions cannot contain more than {MAX_ENTRIES} unique entries."
        )
    return {
        "schema_version": "1.0.0",
        "definition_id": definition_id,
        "name": name,
        "description": description,
        "organism": "Homo sapiens",
        "definition_format": definition_format,
        "identifier_type": identifier_type,
        "set_count": len(sets),
        "requested_identifier_count": sum(item["requested_identifier_count"] for item in sets),
        "unique_identifier_count": total_unique,
        "duplicate_identifier_count": sum(item["duplicate_identifier_count"] for item in sets),
        "weighted": any(item["weighted"] for item in sets),
        "sets": sets,
        "warnings": [],
    }


def _valid_identifier(value: str) -> str:
    normalized = value.strip()
    if not SAFE_IDENTIFIER.fullmatch(normalized):
        raise SignatureDefinitionError(
            "Gene identifiers must contain 1 to 200 printable characters."
        )
    return normalized


def _parse_gene_list(
    text: str, definition_id: str, name: str, description: str | None
) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    if reader.fieldnames is None or "gene_id" not in reader.fieldnames:
        raise SignatureDefinitionError("Gene-list TSV requires a header containing gene_id.")
    unexpected = set(reader.fieldnames) - {"gene_id", "weight"}
    if unexpected:
        raise SignatureDefinitionError(
            f"Gene-list TSV has unsupported columns: {', '.join(sorted(unexpected))}."
        )
    weighted = "weight" in reader.fieldnames
    entries: dict[str, float | None] = {}
    requested = 0
    for row in reader:
        identifier = _valid_identifier(row.get("gene_id", ""))
        requested += 1
        weight: float | None = None
        if weighted:
            raw_weight = (row.get("weight") or "").strip()
            if not raw_weight:
                raise SignatureDefinitionError("Every row in a weighted gene list requires weight.")
            try:
                weight = float(raw_weight)
            except ValueError as error:
                raise SignatureDefinitionError(f"Invalid weight for {identifier}.") from error
            if not math.isfinite(weight):
                raise SignatureDefinitionError(f"Weight for {identifier} must be finite.")
        if identifier in entries and entries[identifier] != weight:
            raise SignatureDefinitionError(
                f"Duplicate identifier {identifier} has conflicting weights."
            )
        entries.setdefault(identifier, weight)
    if not entries:
        raise SignatureDefinitionError("Gene-list TSV does not contain any genes.")
    return _set_document(definition_id, name, description, entries, requested, weighted)


def _parse_gmt(text: str) -> list[dict[str, Any]]:
    sets: list[dict[str, Any]] = []
    names: set[str] = set()
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) < 3:
            raise SignatureDefinitionError(
                f"GMT line {line_number} requires name, description, and genes."
            )
        set_name = _valid_identifier(fields[0])
        if set_name in names:
            raise SignatureDefinitionError(f"GMT set name is duplicated: {set_name}.")
        names.add(set_name)
        identifiers = [_valid_identifier(value) for value in fields[2:]]
        entries = dict.fromkeys(identifiers)
        sets.append(
            _set_document(
                set_name, set_name, fields[1].strip() or None, entries, len(identifiers), False
            )
        )
    if not sets:
        raise SignatureDefinitionError("GMT file does not contain any gene sets.")
    return sets


def _set_document(
    signature_id: str,
    name: str,
    description: str | None,
    entries: dict[str, float | None],
    requested: int,
    weighted: bool,
) -> dict[str, Any]:
    return {
        "signature_id": signature_id,
        "name": name,
        "description": description,
        "requested_identifier_count": requested,
        "unique_identifier_count": len(entries),
        "duplicate_identifier_count": requested - len(entries),
        "weighted": weighted,
        "entries": [
            {"identifier": identifier, **({"weight": weight} if weighted else {})}
            for identifier, weight in entries.items()
        ],
    }


async def list_definitions(session: AsyncSession, project_id: str) -> list[SignatureDefinition]:
    result = await session.scalars(
        select(SignatureDefinition)
        .where(SignatureDefinition.project_id == project_id)
        .order_by(SignatureDefinition.created_at.desc(), SignatureDefinition.id.desc())
    )
    return list(result)


def map_definition(
    definition: SignatureDefinition, prepared: PreparedDataset, bundle_payload: bytes
) -> dict[str, Any]:
    metadata = _feature_metadata(bundle_payload)
    column = definition.identifier_type
    index: dict[str, set[str]] = {}
    for row in metadata:
        raw = row.get(column, "").strip()
        if not raw:
            continue
        key = _normalize(raw, column)
        index.setdefault(key, set()).add(row["feature_id"])
    set_reports = []
    for signature_set in definition.definition_json["sets"]:
        mapped: list[str] = []
        mapped_entries: list[dict[str, str | float]] = []
        missing: list[str] = []
        ambiguous: list[str] = []
        for entry in signature_set["entries"]:
            identifier = entry["identifier"]
            matches = index.get(_normalize(identifier, column), set())
            if len(matches) == 1:
                feature_id = next(iter(matches))
                mapped.append(feature_id)
                mapped_entry: dict[str, str | float] = {
                    "identifier": identifier,
                    "feature_id": feature_id,
                }
                if "weight" in entry:
                    mapped_entry["weight"] = entry["weight"]
                mapped_entries.append(mapped_entry)
            elif not matches:
                missing.append(identifier)
            else:
                ambiguous.append(identifier)
        unique_count = signature_set["unique_identifier_count"]
        set_reports.append(
            {
                "signature_id": signature_set["signature_id"],
                "name": signature_set["name"],
                "requested_identifier_count": signature_set["requested_identifier_count"],
                "unique_identifier_count": unique_count,
                "mapped_identifier_count": len(mapped),
                "missing_identifier_count": len(missing),
                "ambiguous_identifier_count": len(ambiguous),
                "duplicate_identifier_count": signature_set["duplicate_identifier_count"],
                "mapping_coverage": len(mapped) / unique_count,
                "mapped_entries": mapped_entries,
                "mapped_feature_ids": mapped,
                "missing_identifiers": missing,
                "ambiguous_identifiers": ambiguous,
            }
        )
    unique = sum(item["unique_identifier_count"] for item in set_reports)
    mapped = sum(item["mapped_identifier_count"] for item in set_reports)
    return {
        "schema_version": "1.0.0",
        "signature_definition_id": definition.id,
        "prepared_dataset_id": prepared.id,
        "signature_definition_sha256": definition.manifest_sha256,
        "expression_bundle_sha256": hashlib.sha256(bundle_payload).hexdigest(),
        "identifier_type": definition.identifier_type,
        "strip_ensembl_version": definition.identifier_type == "ensembl_gene_id",
        "set_count": len(set_reports),
        "requested_identifier_count": definition.requested_identifier_count,
        "unique_identifier_count": unique,
        "mapped_identifier_count": mapped,
        "missing_identifier_count": sum(item["missing_identifier_count"] for item in set_reports),
        "ambiguous_identifier_count": sum(
            item["ambiguous_identifier_count"] for item in set_reports
        ),
        "duplicate_identifier_count": definition.duplicate_identifier_count,
        "mapping_coverage": mapped / unique,
        "sets": set_reports,
    }


def _normalize(value: str, identifier_type: str) -> str:
    value = value.strip()
    if identifier_type == "ensembl_gene_id":
        return re.sub(r"\.\d+$", "", value).upper()
    return value.upper() if identifier_type == "gene_symbol" else value


def _feature_metadata(payload: bytes) -> list[dict[str, str]]:
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            names = archive.getnames()
            if any(name.startswith("/") or ".." in name.split("/") for name in names):
                raise SignatureDefinitionError("Expression Bundle archive contains unsafe paths.")
            manifest_file = archive.extractfile("expression_bundle/bundle_manifest.json")
            if manifest_file is None:
                raise SignatureDefinitionError("Expression Bundle manifest is missing.")
            manifest = json.load(manifest_file)
            relative = manifest["feature_metadata"]
            metadata_file = archive.extractfile(f"expression_bundle/{relative}")
            if metadata_file is None:
                raise SignatureDefinitionError("Expression Bundle feature metadata is missing.")
            rows = list(
                csv.DictReader(io.TextIOWrapper(metadata_file, encoding="utf-8"), delimiter="\t")
            )
            if not rows or "feature_id" not in rows[0]:
                raise SignatureDefinitionError(
                    "Expression Bundle feature metadata lacks feature_id rows."
                )
            return rows
    except (tarfile.TarError, KeyError, json.JSONDecodeError) as error:
        raise SignatureDefinitionError(
            "Expression Bundle cannot be read for signature mapping."
        ) from error
