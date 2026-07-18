"""Versioned cell-deconvolution method capabilities and input validation."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import math
import tarfile
from datetime import UTC, datetime
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api.models import Analysis, Artifact, Dataset, PreparedDataset, Run
from transcriptforge_api.models.base import new_id
from transcriptforge_api.models.enums import AnalysisType, RunState, RunType
from transcriptforge_api.schemas.analyses import (
    CibersortxImportRequest,
    DeconvolutionCapabilitiesRead,
    DeconvolutionComparisonRead,
    DeconvolutionComparisonRunRead,
    DeconvolutionMethodCapabilityRead,
    DeconvolutionMethodRead,
    DeconvolutionRegistryRead,
)
from transcriptforge_api.storage.base import StorageBackend

_REGISTRY_PATH = Path(__file__).parents[1] / "resources" / "deconvolution_methods.json"
_DECONVOLUTION_RESULTS_SCHEMA = (
    Path(__file__).resolve().parents[4] / "schemas" / "deconvolution_results.schema.json"
)
MAX_CIBERSORTX_RESULT_BYTES = 20 * 1024 * 1024


class CibersortxImportError(ValueError):
    """Raised when an external CIBERSORTx export is unsafe or scientifically incomplete."""


@lru_cache(maxsize=1)
def method_registry() -> DeconvolutionRegistryRead:
    """Load the immutable registry and attach its exact source checksum."""
    source = _REGISTRY_PATH.read_bytes()
    payload = json.loads(source)
    payload["registry_sha256"] = hashlib.sha256(source).hexdigest()
    return DeconvolutionRegistryRead.model_validate(payload)


def prepared_method_capabilities(
    prepared: PreparedDataset, storage: StorageBackend
) -> DeconvolutionCapabilitiesRead:
    """Evaluate registry input declarations against one immutable Expression Bundle."""
    manifest, feature_columns = _bundle_capabilities(storage.read_bytes(prepared.bundle_uri))
    registry = method_registry()
    methods = [_method_capability(method, manifest, feature_columns) for method in registry.methods]
    return DeconvolutionCapabilitiesRead(
        prepared_dataset_id=prepared.id,
        registry_version=registry.registry_version,
        registry_sha256=registry.registry_sha256,
        methods=methods,
    )


def validate_saved_configuration(
    prepared: PreparedDataset,
    storage: StorageBackend,
    *,
    method_id: str,
    assay_name: str,
    reference_profile: str | None,
    minimum_gene_overlap: float,
) -> tuple[DeconvolutionRegistryRead, DeconvolutionMethodRead, dict[str, Any], str]:
    """Resolve and validate a deconvolution design before persistence."""
    manifest, feature_columns = _bundle_capabilities(storage.read_bytes(prepared.bundle_uri))
    registry = method_registry()
    method = next((item for item in registry.methods if item.id == method_id), None)
    if method is None or method.execution_mode != "native":
        raise ValueError(f"Deconvolution method '{method_id}' is not a registered native method.")
    capability = _method_capability(method, manifest, feature_columns)
    if assay_name not in capability.compatible_assays:
        accepted = (
            ", ".join(option.name for option in method.input.assay_options)
            or "external import only"
        )
        raise ValueError(
            f"{method.display_name} cannot use assay '{assay_name}'. Compatible assay types: "
            f"{accepted}."
        )
    if manifest.get("organism") != method.input.organism:
        raise ValueError(
            f"{method.display_name} requires organism '{method.input.organism}', but the "
            f"Expression Bundle declares '{manifest.get('organism', 'unknown')}'."
        )
    if "gene_symbol" not in feature_columns:
        raise ValueError(
            f"{method.display_name} requires an explicit gene_symbol feature-metadata column."
        )
    if minimum_gene_overlap < method.input.minimum_reference_overlap:
        raise ValueError(
            f"{method.display_name} requires minimum_gene_overlap of at least "
            f"{method.input.minimum_reference_overlap:.0%}."
        )
    selected_reference = reference_profile or method.default_reference
    allowed_references = {item.id for item in method.references}
    if selected_reference is None or selected_reference not in allowed_references:
        allowed = ", ".join(sorted(allowed_references))
        raise ValueError(
            f"Reference profile '{selected_reference}' is not valid for {method.display_name}. "
            f"Choose one of: {allowed}."
        )
    assay = next(item for item in manifest["assays"] if item["name"] == assay_name)
    return registry, method, dict(assay), selected_reference


def _method_capability(
    method: DeconvolutionMethodRead,
    manifest: dict[str, Any],
    feature_columns: set[str],
) -> DeconvolutionMethodCapabilityRead:
    reasons: list[str] = []
    compatible_assays: list[str] = []
    organism_compatible = manifest.get("organism") == method.input.organism
    if not organism_compatible:
        reasons.append(f"Expression Bundle organism is not {method.input.organism}.")
    for assay in manifest.get("assays", []):
        matches = any(
            _assay_matches(assay, option.model_dump()) for option in method.input.assay_options
        )
        if matches:
            compatible_assays.append(str(assay["name"]))
    if "gene_symbol" not in feature_columns:
        reasons.append("Expression Bundle feature metadata does not contain gene_symbol.")
    if not compatible_assays:
        requested = ", ".join(option.name for option in method.input.assay_options)
        reasons.append(f"No compatible assay is available; this method requires {requested}.")
    if method.implementation_status != "available":
        reasons.append(
            "Upstream license acceptance and a user-supplied EPIC installation are required."
            if method.implementation_status == "license_blocked"
            else "Scientific runner is not implemented yet."
        )
    if method.execution_mode == "external_import" and not reasons:
        reasons.append(
            "External import only: TranscriptForge will not execute CIBERSORTx or handle "
            "credentials."
        )
    return DeconvolutionMethodCapabilityRead(
        method=method,
        compatible_assays=compatible_assays,
        configuration_available=(
            bool(compatible_assays)
            and "gene_symbol" in feature_columns
            and manifest.get("organism") == method.input.organism
            and (
                method.execution_mode == "native"
                or method.implementation_status == "available"
            )
        ),
        execution_available=(
            method.execution_mode == "native" and method.implementation_status == "available"
        ),
        blocked_reasons=reasons,
    )


def _assay_matches(assay: dict[str, Any], option: dict[str, Any]) -> bool:
    return (
        assay.get("name") == option["name"]
        and assay.get("scale") in option["scales"]
        and assay.get("value_type") in option["value_types"]
        and assay.get("feature_level") == "gene"
    )


def _bundle_capabilities(bundle: bytes) -> tuple[dict[str, Any], set[str]]:
    try:
        with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:gz") as archive:
            manifest_member = archive.extractfile("expression_bundle/bundle_manifest.json")
            if manifest_member is None:
                raise ValueError("Expression Bundle manifest is unavailable.")
            manifest = json.load(manifest_member)
            feature_path = manifest.get("feature_metadata")
            if not isinstance(feature_path, str):
                raise ValueError("Expression Bundle feature metadata path is unavailable.")
            feature_member = archive.extractfile(f"expression_bundle/{feature_path}")
            if feature_member is None:
                raise ValueError("Expression Bundle feature metadata is unavailable.")
            text = io.TextIOWrapper(feature_member, encoding="utf-8", newline="")
            reader = csv.reader(text, delimiter="\t")
            columns = set(next(reader, []))
    except tarfile.TarError as error:
        raise ValueError("Expression Bundle archive is unreadable.") from error
    if not isinstance(manifest.get("assays"), list):
        raise ValueError("Expression Bundle does not declare its assays.")
    return manifest, columns


async def import_cibersortx_result(
    session: AsyncSession,
    storage: StorageBackend,
    prepared: PreparedDataset,
    request: CibersortxImportRequest,
    *,
    source_filename: str,
    source: bytes,
) -> Analysis:
    """Validate and persist one externally executed CIBERSORTx relative-mode result."""
    if not source or len(source) > MAX_CIBERSORTX_RESULT_BYTES:
        raise CibersortxImportError(
            f"CIBERSORTx result must be between 1 byte and {MAX_CIBERSORTX_RESULT_BYTES} bytes."
        )
    source_filename = Path(source_filename).name.strip()
    if not source_filename or len(source_filename) > 500:
        raise CibersortxImportError("CIBERSORTx source filename is blank or too long.")
    dataset = await session.get(Dataset, prepared.dataset_id)
    if dataset is None:
        raise CibersortxImportError("The source dataset no longer exists.")
    bundle = await asyncio.to_thread(storage.read_bytes, prepared.bundle_uri)
    manifest, sample_ids, assay = _cibersortx_bundle_context(bundle, request.assay)
    if len(sample_ids) != prepared.sample_count:
        raise CibersortxImportError(
            "Expression Bundle sample metadata does not match the prepared-dataset sample count."
        )
    cell_types, values = _parse_cibersortx_relative_table(source, sample_ids)
    registry = method_registry()
    method = next(item for item in registry.methods if item.id == "cibersortx_external")
    capability = _method_capability(
        method,
        manifest,
        _bundle_capabilities(bundle)[1],
    )
    if request.assay not in capability.compatible_assays:
        raise CibersortxImportError(
            f"CIBERSORTx import requires a compatible linear nonnegative TPM assay; "
            f"'{request.assay}' is not compatible."
        )

    analysis_id = new_id()
    run_id = new_id()
    source_sha256 = hashlib.sha256(source).hexdigest()
    bundle_sha256 = hashlib.sha256(bundle).hexdigest()
    overlap_fraction = request.overlap_gene_count / request.signature.gene_count
    imported_at = datetime.now(UTC)
    external_record = {
        "source_filename": source_filename,
        "source_sha256": source_sha256,
        "source_size_bytes": len(source),
        "mode": request.mode,
        "values_declared_as": "relative_fraction",
        "batch_correction": request.batch_correction,
        "permutations": request.permutations,
        "signature": request.signature.model_dump(mode="json"),
        "runtime": {
            "platform": "CIBERSORTx",
            **request.runtime.model_dump(mode="json"),
        },
    }
    frozen_import = {
        "schema_version": "1.0.0",
        "analysis_id": analysis_id,
        "run_id": run_id,
        "prepared_dataset_id": prepared.id,
        "assay": assay,
        "expression_bundle_sha256": bundle_sha256,
        "external_import": external_record,
        "mixture_gene_count": request.mixture_gene_count,
        "overlap_gene_count": request.overlap_gene_count,
    }
    frozen_import_bytes = _json_bytes(frozen_import)
    request_sha256 = hashlib.sha256(frozen_import_bytes).hexdigest()
    estimates = [
        {
            "sample_id": sample_id,
            "cell_type_id": cell_type,
            "value": values[sample_id][cell_type],
        }
        for sample_id in sample_ids
        for cell_type in cell_types
    ]
    composition_summaries = []
    for sample_id in sample_ids:
        reported_sum = sum(values[sample_id].values())
        composition_summaries.append(
            {
                "sample_id": sample_id,
                "reported_sum": reported_sum,
                "residual_fraction": max(0.0, 1.0 - reported_sum),
                "within_tolerance": abs(reported_sum - 1.0) <= 0.02,
            }
        )
    result = {
        "schema_version": "1.0.0",
        "analysis_id": analysis_id,
        "prepared_dataset_id": prepared.id,
        "method": "cibersortx_external",
        "method_registry_version": registry.registry_version,
        "method_registry_sha256": registry.registry_sha256,
        "result_type": "cell_fraction",
        "quantity_label": method.quantity_label,
        "unit": "fraction",
        "composition_constraint": "declared_by_import",
        "input_validation": {
            "assay": assay["name"],
            "scale": assay["scale"],
            "value_type": assay["value_type"],
            "feature_level": assay["feature_level"],
            "identifier_namespace": "gene_symbol",
            "input_feature_count": request.mixture_gene_count,
            "mapped_feature_count": request.mixture_gene_count,
            "blank_symbol_count": 0,
            "duplicate_symbol_count": 0,
            "reference_gene_count": request.signature.gene_count,
            "overlap_gene_count": request.overlap_gene_count,
            "overlap_fraction": overlap_fraction,
            "minimum_overlap_fraction": 0.0,
            "passed": True,
        },
        "reference": {
            "id": request.signature.name,
            "version": request.signature.version,
            "sha256": request.signature.sha256,
            "cell_type_count": len(cell_types),
        },
        "cell_types": [{"id": item, "label": item} for item in cell_types],
        "sample_ids": sample_ids,
        "estimates": estimates,
        "composition_summaries": composition_summaries,
        "warnings": [
            "Imported external CIBERSORTx result; TranscriptForge did not execute or independently "
            "reproduce the upstream computation.",
            "Values were explicitly declared as relative fractions and are tied to the supplied "
            "signature, runtime, source checksum, and Expression Bundle assay provenance.",
        ],
        "software": {
            "language": "external service",
            "language_version": request.runtime.version,
            "packages": {"CIBERSORTx": request.runtime.version},
        },
        "provenance": {
            "expression_bundle_sha256": bundle_sha256,
            "analysis_request_sha256": request_sha256,
            "reference_sha256": request.signature.sha256,
            "external_source_sha256": source_sha256,
        },
        "external_import": external_record,
    }
    _validate_deconvolution_result(result)
    normalized_table = _normalized_fraction_table(sample_ids, cell_types, values)
    manifest_payload = {
        "schema_version": "1.0.0",
        "analysis_type": "deconvolution",
        "title": "Imported CIBERSORTx relative fractions",
        "summary_metrics": [
            {"label": "Samples", "value": len(sample_ids)},
            {"label": "Cell populations", "value": len(cell_types)},
            {"label": "Signature overlap", "value": f"{overlap_fraction:.1%}"},
            {"label": "External runtime", "value": request.runtime.version},
        ],
        "sections": [
            {
                "id": "cell_fractions",
                "title": "Externally estimated relative fractions",
                "items": [
                    {
                        "type": "table",
                        "title": "Normalized relative-fraction table",
                        "path": "deconvolution_estimates.tsv",
                    }
                ],
            }
        ],
        "downloads": [
            {
                "type": "file",
                "title": "Original CIBERSORTx export",
                "path": "cibersortx_source.txt",
            },
            {
                "type": "file",
                "title": "Frozen external-import provenance",
                "path": "external_import_provenance.json",
            },
            {
                "type": "file",
                "title": "Structured deconvolution results",
                "path": "deconvolution_results.json",
            },
        ],
        "warnings": result["warnings"],
    }
    configuration = {
        "analysis_type": "deconvolution",
        "method": "cibersortx_external",
        "assay": request.assay,
        "parameters": {
            "reference_profile": request.signature.name,
            "minimum_gene_overlap": overlap_fraction,
            "tumor_mode": False,
            "scale_mrna": False,
        },
        "random_seed": 0,
        "method_registry_version": registry.registry_version,
        "method_registry_sha256": registry.registry_sha256,
        "method_spec": method.model_dump(mode="json"),
        "input_assay_descriptor": assay,
        "result_type": "cell_fraction",
        "execution_available": False,
        "external_import": external_record,
    }
    analysis = Analysis(
        id=analysis_id,
        project_id=dataset.project_id,
        prepared_dataset_id=prepared.id,
        analysis_type=AnalysisType.DECONVOLUTION.value,
        name=request.analysis_name.strip(),
        description="Externally executed CIBERSORTx relative-mode result import.",
        configuration_json=configuration,
    )
    run = Run(
        id=run_id,
        run_type=RunType.ANALYSIS.value,
        dataset_id=prepared.dataset_id,
        prepared_dataset_id=prepared.id,
        analysis_id=analysis_id,
        state=RunState.SUCCEEDED.value,
        profile="external_import",
        params_uri="pending://external-import-provenance",
        output_uri="pending://external-import-result",
        work_uri="pending://external-import-source",
        exit_code=0,
        started_at=imported_at,
        finished_at=imported_at,
    )
    namespace = ("projects", dataset.project_id, "analyses", analysis_id, "runs", run_id)
    stored_objects = []
    try:
        stored_source = await asyncio.to_thread(
            storage.put, namespace, source_filename, io.BytesIO(source)
        )
        stored_objects.append(stored_source)
        stored_provenance = await asyncio.to_thread(
            storage.put,
            namespace,
            "external_import_provenance.json",
            io.BytesIO(frozen_import_bytes),
        )
        stored_objects.append(stored_provenance)
        stored_result = await asyncio.to_thread(
            storage.put,
            namespace,
            "deconvolution_results.json",
            io.BytesIO(_json_bytes(result)),
        )
        stored_objects.append(stored_result)
        stored_estimates = await asyncio.to_thread(
            storage.put,
            namespace,
            "deconvolution_estimates.tsv",
            io.BytesIO(normalized_table),
        )
        stored_objects.append(stored_estimates)
        stored_manifest = await asyncio.to_thread(
            storage.put,
            namespace,
            "result_manifest.json",
            io.BytesIO(_json_bytes(manifest_payload)),
        )
        stored_objects.append(stored_manifest)
        run.params_uri = stored_provenance.uri
        run.output_uri = stored_result.uri
        run.work_uri = stored_source.uri
        session.add(analysis)
        await session.flush()
        session.add(run)
        await session.flush()
        artifacts = [
            (
                "result_manifest",
                "Result manifest",
                "result_manifest.json",
                "application/json",
                0,
                stored_manifest,
            ),
            (
                "deconvolution_results",
                "Structured CIBERSORTx fractions",
                "deconvolution_results.json",
                "application/json",
                1,
                stored_result,
            ),
            (
                "deconvolution_estimates",
                "Normalized relative-fraction table",
                "deconvolution_estimates.tsv",
                "text/tab-separated-values",
                2,
                stored_estimates,
            ),
            (
                "cibersortx_source",
                "Original CIBERSORTx export",
                "cibersortx_source.txt",
                "text/plain",
                3,
                stored_source,
            ),
            (
                "external_import_provenance",
                "Frozen CIBERSORTx import provenance",
                "external_import_provenance.json",
                "application/json",
                4,
                stored_provenance,
            ),
        ]
        for artifact_type, title, relative_path, mime_type, order, stored in artifacts:
            session.add(
                Artifact(
                    run_id=run_id,
                    artifact_type=artifact_type,
                    title=title,
                    relative_path=relative_path,
                    storage_uri=stored.uri,
                    mime_type=mime_type,
                    size_bytes=stored.size_bytes,
                    sha256=stored.sha256,
                    display_order=order,
                    metadata_json={"external_import": True},
                )
            )
        await session.commit()
        await session.refresh(analysis)
        return analysis
    except Exception:
        await session.rollback()
        for stored in stored_objects:
            await asyncio.to_thread(storage.delete, stored.uri)
        raise


def _cibersortx_bundle_context(
    bundle: bytes, assay_name: str
) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    try:
        with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:gz") as archive:
            manifest_member = archive.extractfile("expression_bundle/bundle_manifest.json")
            if manifest_member is None:
                raise CibersortxImportError("Expression Bundle manifest is unavailable.")
            manifest = json.load(manifest_member)
            metadata_path = manifest.get("sample_metadata")
            if not isinstance(metadata_path, str):
                raise CibersortxImportError("Expression Bundle sample metadata is unavailable.")
            metadata_member = archive.extractfile(f"expression_bundle/{metadata_path}")
            if metadata_member is None:
                raise CibersortxImportError("Expression Bundle sample metadata is unavailable.")
            reader = csv.DictReader(
                io.TextIOWrapper(metadata_member, encoding="utf-8-sig", newline=""),
                delimiter="\t",
            )
            if reader.fieldnames is None or "sample_id" not in reader.fieldnames:
                raise CibersortxImportError("Sample metadata must contain sample_id.")
            sample_ids = [row.get("sample_id", "").strip() for row in reader]
    except (tarfile.TarError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CibersortxImportError("Expression Bundle archive is unreadable.") from error
    if (
        not sample_ids
        or any(not item for item in sample_ids)
        or len(set(sample_ids)) != len(sample_ids)
    ):
        raise CibersortxImportError(
            "Expression Bundle sample identifiers are invalid or duplicated."
        )
    assay = next(
        (item for item in manifest.get("assays", []) if item.get("name") == assay_name),
        None,
    )
    if not isinstance(assay, dict):
        raise CibersortxImportError(
            f"Assay '{assay_name}' is not present in the Expression Bundle."
        )
    return manifest, sample_ids, dict(assay)


def _parse_cibersortx_relative_table(
    source: bytes, expected_sample_ids: list[str]
) -> tuple[list[str], dict[str, dict[str, float]]]:
    try:
        text = source.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CibersortxImportError("CIBERSORTx result must be UTF-8 text.") from error
    if "\x00" in text:
        raise CibersortxImportError("CIBERSORTx result contains NUL bytes.")
    first_line = text.splitlines()[0] if text.splitlines() else ""
    delimiter = "\t" if first_line.count("\t") >= first_line.count(",") else ","
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    if len(rows) < 2:
        raise CibersortxImportError("CIBERSORTx result requires a header and at least one sample.")
    header = [item.strip() for item in rows[0]]
    if not header or header[0].casefold() != "mixture":
        raise CibersortxImportError("The first CIBERSORTx result column must be 'Mixture'.")
    if any(not item for item in header) or len(set(header)) != len(header):
        raise CibersortxImportError("CIBERSORTx result columns are blank or duplicated.")
    diagnostics = {
        "p-value",
        "p.value",
        "correlation",
        "rmse",
        "absolute score (sig.score)",
    }
    cell_indexes = [
        index for index, label in enumerate(header[1:], 1) if label.casefold() not in diagnostics
    ]
    cell_types = [header[index] for index in cell_indexes]
    if not cell_types:
        raise CibersortxImportError("CIBERSORTx result contains no cell-fraction columns.")
    values: dict[str, dict[str, float]] = {}
    for line_number, row in enumerate(rows[1:], 2):
        if not row or all(not item.strip() for item in row):
            continue
        if len(row) != len(header):
            raise CibersortxImportError(
                f"CIBERSORTx result row {line_number} has {len(row)} columns; expected "
                f"{len(header)}."
            )
        sample_id = row[0].strip()
        if not sample_id or sample_id in values:
            raise CibersortxImportError(
                f"CIBERSORTx result row {line_number} has a blank or duplicate sample identifier."
            )
        fractions: dict[str, float] = {}
        for index, cell_type in zip(cell_indexes, cell_types, strict=True):
            try:
                value = float(row[index])
            except ValueError as error:
                raise CibersortxImportError(
                    f"CIBERSORTx value at row {line_number}, column '{cell_type}' is not numeric."
                ) from error
            if not math.isfinite(value) or value < 0 or value > 1:
                raise CibersortxImportError(
                    f"CIBERSORTx value at row {line_number}, column '{cell_type}' must be a "
                    "finite fraction between 0 and 1."
                )
            fractions[cell_type] = value
        reported_sum = sum(fractions.values())
        if abs(reported_sum - 1.0) > 0.02:
            raise CibersortxImportError(
                f"CIBERSORTx relative fractions for '{sample_id}' sum to {reported_sum:.6g}; "
                "expected 1 within 0.02."
            )
        values[sample_id] = fractions
    expected = set(expected_sample_ids)
    observed = set(values)
    if observed != expected:
        missing = sorted(expected - observed)
        unexpected = sorted(observed - expected)
        details = []
        if missing:
            details.append("missing: " + ", ".join(missing[:10]))
        if unexpected:
            details.append("unexpected: " + ", ".join(unexpected[:10]))
        raise CibersortxImportError(
            "CIBERSORTx sample identifiers must exactly match the Expression Bundle ("
            + "; ".join(details)
            + ")."
        )
    return cell_types, values


def _normalized_fraction_table(
    sample_ids: list[str],
    cell_types: list[str],
    values: dict[str, dict[str, float]],
) -> bytes:
    target = io.StringIO(newline="")
    writer = csv.writer(target, delimiter="\t", lineterminator="\n")
    writer.writerow(["sample_id", *cell_types])
    for sample_id in sample_ids:
        writer.writerow(
            [sample_id, *(format(values[sample_id][item], ".17g") for item in cell_types)]
        )
    return target.getvalue().encode()


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def _validate_deconvolution_result(payload: dict[str, Any]) -> None:
    schema = json.loads(_DECONVOLUTION_RESULTS_SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda item: list(item.path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(item) for item in first.absolute_path) or "root"
        raise CibersortxImportError(
            f"Imported result violates deconvolution_results.schema.json at {location}: "
            f"{first.message}"
        )


async def deconvolution_comparison(
    session: AsyncSession,
    storage: StorageBackend,
    prepared_dataset_id: str,
) -> DeconvolutionComparisonRead:
    """Compare latest successful deconvolution runs without crossing semantic boundaries."""
    rows = (
        await session.execute(
            select(Run, Analysis, Artifact)
            .join(Analysis, Run.analysis_id == Analysis.id)
            .join(Artifact, Artifact.run_id == Run.id)
            .where(
                Run.prepared_dataset_id == prepared_dataset_id,
                Run.state == RunState.SUCCEEDED.value,
                Analysis.analysis_type == AnalysisType.DECONVOLUTION.value,
                Artifact.artifact_type == "deconvolution_results",
            )
            .order_by(Run.created_at.desc(), Artifact.id.asc())
        )
    ).all()
    latest: list[tuple[Run, Analysis, Artifact]] = []
    seen_analyses: set[str] = set()
    for run, analysis, artifact in rows:
        if analysis.id in seen_analyses:
            continue
        seen_analyses.add(analysis.id)
        latest.append((run, analysis, artifact))

    comparison_runs: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    for run, analysis, artifact in latest:
        try:
            source = await asyncio.to_thread(storage.read_bytes, artifact.storage_uri)
            payload = json.loads(source)
            candidate = _comparison_run(prepared_dataset_id, run, analysis, artifact, payload)
            expression_bundle_sha256 = candidate.pop("_expression_bundle_sha256")
            validated = DeconvolutionComparisonRunRead.model_validate(candidate).model_dump(
                mode="json"
            )
            validated["_expression_bundle_sha256"] = expression_bundle_sha256
            comparison_runs.append(validated)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            exclusions.append(
                {
                    "analysis_id": analysis.id,
                    "analysis_name": analysis.name,
                    "run_id": run.id,
                    "reason": f"Result artifact is not comparison-ready: {error}",
                }
            )

    grouped: dict[str, list[dict[str, Any]]] = {}
    group_keys: dict[str, dict[str, Any]] = {}
    for item in comparison_runs:
        key = {
            "result_type": item["result_type"],
            "unit": item["unit"],
            "assay": item["assay"],
            "sample_ids": item["sample_ids"],
            "expression_bundle_sha256": item.pop("_expression_bundle_sha256"),
        }
        encoded = json.dumps(key, sort_keys=True, separators=(",", ":"))
        section_id = hashlib.sha256(encoded.encode()).hexdigest()[:16]
        grouped.setdefault(section_id, []).append(item)
        group_keys[section_id] = key

    sections = [
        _comparison_section(section_id, group_keys[section_id], runs)
        for section_id, runs in grouped.items()
    ]
    sections.sort(key=lambda item: (item["result_type"], item["assay"]["name"], item["id"]))
    return DeconvolutionComparisonRead.model_validate(
        {
            "schema_version": "1.0.0",
            "prepared_dataset_id": prepared_dataset_id,
            "latest_successful_run_count": len(latest),
            "sections": sections,
            "exclusions": exclusions,
            "interpretation": (
                "Only runs with identical result units, assay semantics, sample order, and "
                "Expression Bundle identity share a section. References remain method-specific, "
                "and population matching is exact rather than inferred through an undocumented "
                "crosswalk."
            ),
        }
    )


def _comparison_run(
    prepared_dataset_id: str,
    run: Run,
    analysis: Analysis,
    artifact: Artifact,
    payload: Any,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("root must be an object")
    if payload.get("prepared_dataset_id") != prepared_dataset_id:
        raise ValueError("prepared dataset identity differs")
    sample_ids = _unique_strings(payload.get("sample_ids"), "sample_ids")
    cell_type_payload = payload.get("cell_types")
    if not isinstance(cell_type_payload, list) or not cell_type_payload:
        raise ValueError("cell_types must be a non-empty array")
    cell_types: list[dict[str, str]] = []
    for entry in cell_type_payload:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("id"), str)
            or not isinstance(entry.get("label"), str)
        ):
            raise ValueError("cell_types contain an invalid entry")
        cell_types.append({"id": entry["id"], "label": entry["label"]})
    if len({item["id"] for item in cell_types}) != len(cell_types):
        raise ValueError("cell type identifiers are duplicated")

    estimate_payload = payload.get("estimates")
    if not isinstance(estimate_payload, list):
        raise ValueError("estimates must be an array")
    estimates: list[dict[str, Any]] = []
    observed: set[tuple[str, str]] = set()
    allowed_samples = set(sample_ids)
    allowed_cell_types = {item["id"] for item in cell_types}
    for entry in estimate_payload:
        if not isinstance(entry, dict):
            raise ValueError("estimates contain an invalid entry")
        sample_id = entry.get("sample_id")
        cell_type_id = entry.get("cell_type_id")
        value = entry.get("value")
        if (
            not isinstance(sample_id, str)
            or not isinstance(cell_type_id, str)
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or sample_id not in allowed_samples
            or cell_type_id not in allowed_cell_types
            or (sample_id, cell_type_id) in observed
        ):
            raise ValueError("estimates contain an invalid or duplicate value")
        observed.add((sample_id, cell_type_id))
        estimates.append(
            {"sample_id": sample_id, "cell_type_id": cell_type_id, "value": float(value)}
        )
    if len(observed) != len(sample_ids) * len(cell_types):
        raise ValueError("estimates do not form a complete sample-by-population matrix")

    validation = _object(payload, "input_validation")
    assay = {
        "name": _string(validation, "assay"),
        "scale": _string(validation, "scale"),
        "value_type": _string(validation, "value_type"),
        "feature_level": _string(validation, "feature_level"),
        "identifier_namespace": _string(validation, "identifier_namespace"),
    }
    reference = _object(payload, "reference")
    provenance = _object(payload, "provenance")
    configuration = analysis.configuration_json
    method_spec = configuration.get("method_spec", {})
    display_name = method_spec.get("display_name", payload.get("method"))
    if not isinstance(display_name, str):
        raise ValueError("method display name is missing")
    overlap = validation.get("overlap_fraction")
    if isinstance(overlap, bool) or not isinstance(overlap, (int, float)):
        raise ValueError("reference overlap is missing")
    return {
        "analysis_id": analysis.id,
        "analysis_name": analysis.name,
        "run_id": run.id,
        "method": _string(payload, "method"),
        "display_name": display_name,
        "result_type": _string(payload, "result_type"),
        "quantity_label": _string(payload, "quantity_label"),
        "unit": _string(payload, "unit"),
        "composition_constraint": _string(payload, "composition_constraint"),
        "assay": assay,
        "reference": {
            "id": _string(reference, "id"),
            "version": _string(reference, "version"),
            "sha256": _string(reference, "sha256"),
        },
        "reference_overlap_fraction": float(overlap),
        "sample_ids": sample_ids,
        "cell_types": cell_types,
        "estimates": estimates,
        "result_sha256": artifact.sha256,
        "method_registry_version": _string(payload, "method_registry_version"),
        "method_registry_sha256": _string(payload, "method_registry_sha256"),
        "_expression_bundle_sha256": _string(provenance, "expression_bundle_sha256"),
    }


def _comparison_section(
    section_id: str,
    key: dict[str, Any],
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    runs.sort(key=lambda item: (item["display_name"].casefold(), item["analysis_name"].casefold()))
    first_labels = {item["id"]: item["label"] for item in runs[0]["cell_types"]}
    shared_ids = set(first_labels)
    for run in runs[1:]:
        labels = {item["id"]: item["label"] for item in run["cell_types"]}
        shared_ids &= {
            cell_type_id
            for cell_type_id, label in labels.items()
            if first_labels.get(cell_type_id) == label
        }
    shared_cell_types = [
        {"id": item["id"], "label": item["label"]}
        for item in runs[0]["cell_types"]
        if item["id"] in shared_ids
    ]
    correlations: list[dict[str, Any]] = []
    if len(key["sample_ids"]) >= 3:
        for left, right in combinations(runs, 2):
            if left["method"] == right["method"]:
                continue
            left_values = {
                (item["sample_id"], item["cell_type_id"]): item["value"]
                for item in left["estimates"]
            }
            right_values = {
                (item["sample_id"], item["cell_type_id"]): item["value"]
                for item in right["estimates"]
            }
            for cell_type in shared_cell_types:
                left_vector = [
                    left_values[(sample_id, cell_type["id"])] for sample_id in key["sample_ids"]
                ]
                right_vector = [
                    right_values[(sample_id, cell_type["id"])] for sample_id in key["sample_ids"]
                ]
                correlation = _pearson(left_vector, right_vector)
                if correlation is not None:
                    correlations.append(
                        {
                            "left_run_id": left["run_id"],
                            "right_run_id": right["run_id"],
                            "left_method": left["display_name"],
                            "right_method": right["display_name"],
                            "cell_type_id": cell_type["id"],
                            "cell_type_label": cell_type["label"],
                            "sample_count": len(key["sample_ids"]),
                            "pearson_correlation": correlation,
                        }
                    )

    constraints = sorted({item["composition_constraint"] for item in runs})
    references = sorted({item["reference"]["id"] for item in runs})
    warnings = [
        "Reference profiles remain method-specific; only exact population identifiers and labels "
        "are matched."
    ]
    if len(runs) < 2:
        warnings.append("Run another compatible method to calculate cross-method concordance.")
    if len(runs) >= 2 and not shared_cell_types:
        warnings.append("Compatible runs have no exact shared population identifiers/labels.")
    if len(references) > 1:
        warnings.append(
            "Methods use different declared references; no reference crosswalk was inferred."
        )
    if len(constraints) > 1:
        warnings.append("Fraction composition constraints differ and remain visible per run.")
    if key["result_type"] == "enrichment_score":
        warnings.append(
            "Raw enrichment magnitudes are method-specific; Pearson correlations assess only the "
            "within-population pattern across the same samples."
        )
    return {
        "id": section_id,
        "result_type": key["result_type"],
        "unit": key["unit"],
        "composition_constraints": constraints,
        "comparison_mode": (
            "fraction_pattern"
            if key["result_type"] == "cell_fraction"
            else "within_population_pattern"
        ),
        "assay": key["assay"],
        "sample_ids": key["sample_ids"],
        "shared_cell_types": shared_cell_types,
        "reference_mode": "method_specific_exact_population_intersection",
        "runs": runs,
        "correlations": correlations,
        "warnings": warnings,
    }


def _pearson(left: list[float], right: list[float]) -> float | None:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    left_centered = [value - left_mean for value in left]
    right_centered = [value - right_mean for value in right]
    denominator = math.sqrt(
        sum(value * value for value in left_centered)
        * sum(value * value for value in right_centered)
    )
    if denominator <= 0:
        return None
    observed = (
        sum(
            left_value * right_value
            for left_value, right_value in zip(left_centered, right_centered, strict=True)
        )
        / denominator
    )
    return max(-1.0, min(1.0, observed))


def _object(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _string(source: dict[str, Any], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _unique_strings(value: Any, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError(f"{label} must contain unique non-empty strings")
    return value
