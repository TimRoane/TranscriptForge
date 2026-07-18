"""Versioned cell-deconvolution method capabilities and input validation."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import tarfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from transcriptforge_api.models import PreparedDataset
from transcriptforge_api.schemas.analyses import (
    DeconvolutionCapabilitiesRead,
    DeconvolutionMethodCapabilityRead,
    DeconvolutionMethodRead,
    DeconvolutionRegistryRead,
)
from transcriptforge_api.storage.base import StorageBackend

_REGISTRY_PATH = Path(__file__).parents[1] / "resources" / "deconvolution_methods.json"


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
    if method.execution_mode == "external_import":
        reasons.append("External-result import adapter is not implemented yet.")
    else:
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
            reasons.append("Scientific runner is not implemented yet.")
    return DeconvolutionMethodCapabilityRead(
        method=method,
        compatible_assays=compatible_assays,
        configuration_available=(
            method.execution_mode == "native"
            and bool(compatible_assays)
            and "gene_symbol" in feature_columns
            and manifest.get("organism") == method.input.organism
        ),
        execution_available=method.implementation_status == "available",
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
