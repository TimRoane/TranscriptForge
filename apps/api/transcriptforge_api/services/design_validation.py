"""Metadata-aware differential-expression design validation."""

import csv
import json
import tarfile
from collections import Counter
from io import BytesIO, TextIOWrapper
from typing import Literal

import numpy as np

from transcriptforge_api.models import PreparedDataset
from transcriptforge_api.schemas.analyses import (
    DesignCellRead,
    DesignOptionsRead,
    DesignValidationRead,
    DifferentialExpressionPreviewRequest,
    MetadataVariableRead,
)
from transcriptforge_api.storage.base import StorageBackend

_MISSING = {"", "na", "nan", "null", "none"}


def design_options(
    prepared: PreparedDataset, storage: StorageBackend
) -> tuple[list[dict[str, str]], DesignOptionsRead]:
    """Read immutable sample metadata and describe selectable design variables."""
    rows = _read_bundle_metadata(storage.read_bytes(prepared.bundle_uri))
    variables = []
    for name in rows[0]:
        if name == "sample_id":
            continue
        values = [row.get(name, "").strip() for row in rows]
        present = [value for value in values if value.lower() not in _MISSING]
        kind = _variable_kind(present)
        unique_values = sorted(set(present))
        # Binary numeric encodings such as 0/1 are valid classifier outcomes and still
        # need named choices in the UI. Higher-cardinality numeric variables remain
        # level-free so continuous metadata is not presented as categorical.
        levels = unique_values if kind == "categorical" or len(unique_values) == 2 else []
        variables.append(
            MetadataVariableRead(
                name=name,
                kind=kind,
                levels=levels,
                missing_count=len(values) - len(present),
                unique_count=len(unique_values),
            )
        )
    return rows, DesignOptionsRead(
        sample_count=len(rows),
        assays=list(prepared.value_types_available),
        variables=variables,
    )


def validate_design(
    prepared: PreparedDataset,
    storage: StorageBackend,
    request: DifferentialExpressionPreviewRequest,
) -> DesignValidationRead:
    """Resolve method routing and reject invalid or rank-deficient designs."""
    rows, options = design_options(prepared, storage)
    errors: list[str] = []
    warnings: list[str] = []
    if request.assay not in prepared.value_types_available:
        errors.append(f"Assay '{request.assay}' is not available in this Expression Bundle.")
    resolved_method = _resolve_method(request.assay, request.method, errors)
    parameters = request.parameters
    design = parameters.design
    contrast = parameters.contrast
    terms = [*([design.block_column] if design.block_column else []), *design.covariates]
    if design.primary_variable not in terms:
        terms.append(design.primary_variable)
    known = {variable.name: variable for variable in options.variables}
    for term in terms:
        if term not in known:
            errors.append(f"Design variable '{term}' is not present in sample metadata.")
    for left, right in design.interaction_terms:
        if left not in known or right not in known:
            errors.append(f"Interaction '{left}:{right}' references a missing variable.")
    if contrast.variable not in known:
        errors.append(f"Contrast variable '{contrast.variable}' is not present in metadata.")

    formula = _formula(terms, design.interaction_terms)
    contrast_label = (
        f"{contrast.numerator} versus {contrast.denominator} within {contrast.variable}"
    )
    contrast_counts: dict[str, int] = {}
    matrix_columns = ["Intercept"]
    matrix = np.ones((len(rows), 1), dtype=np.float64)
    encodings: dict[str, tuple[list[str], np.ndarray[tuple[int, int], np.dtype[np.float64]]]] = {}

    for term in terms:
        if term not in known:
            continue
        values = [row[term].strip() for row in rows]
        if any(value.lower() in _MISSING for value in values):
            errors.append(f"Design variable '{term}' contains missing values.")
            continue
        variable = known[term]
        # Blocking variables represent experimental units even when their labels happen
        # to be numeric (for example donor IDs 71, 77, 91, and 93). Treating those
        # labels as a continuous covariate would silently change a paired design.
        kind: Literal["categorical", "numeric"] = (
            "categorical" if term == design.block_column else variable.kind
        )
        if variable.unique_count < 2:
            errors.append(f"Design variable '{term}' has only one observed value.")
            continue
        names, columns = _encode_term(
            term,
            values,
            kind,
            design.reference_levels.get(term),
            errors,
        )
        encodings[term] = (names, columns)
        matrix_columns.extend(names)
        matrix = np.column_stack((matrix, columns))

    for left, right in design.interaction_terms:
        if left not in encodings or right not in encodings:
            continue
        left_names, left_columns = encodings[left]
        right_names, right_columns = encodings[right]
        interaction_columns = []
        interaction_names = []
        for left_index, left_name in enumerate(left_names):
            for right_index, right_name in enumerate(right_names):
                interaction_names.append(f"{left_name}:{right_name}")
                interaction_columns.append(
                    left_columns[:, left_index] * right_columns[:, right_index]
                )
        if interaction_columns:
            joined = np.column_stack(interaction_columns)
            matrix_columns.extend(interaction_names)
            matrix = np.column_stack((matrix, joined))

    if contrast.variable in known:
        primary_values = [row.get(contrast.variable, "") for row in rows]
        counts = Counter(primary_values)
        contrast_counts = {
            contrast.numerator: counts[contrast.numerator],
            contrast.denominator: counts[contrast.denominator],
        }
        for level in (contrast.numerator, contrast.denominator):
            if level not in counts:
                errors.append(f"Contrast level '{level}' is absent from '{contrast.variable}'.")
            elif counts[level] < parameters.minimum_samples:
                errors.append(
                    f"Contrast level '{level}' has {counts[level]} sample(s); "
                    f"at least {parameters.minimum_samples} are required."
                )
        if counts[contrast.numerator] and counts[contrast.denominator]:
            ratio = min(counts[contrast.numerator], counts[contrast.denominator]) / max(
                counts[contrast.numerator], counts[contrast.denominator]
            )
            if ratio < 0.25:
                warnings.append("The selected contrast is severely imbalanced between groups.")

    rank = int(np.linalg.matrix_rank(matrix))
    if rank < matrix.shape[1]:
        errors.append(
            f"The design matrix is rank deficient ({rank} independent columns for "
            f"{matrix.shape[1]} model columns). Remove confounded or redundant terms."
        )
    if matrix.shape[1] >= len(rows):
        warnings.append("The design uses nearly as many model columns as samples.")

    cell_terms = [*design.covariates, design.primary_variable]
    cells = _design_cells(rows, [term for term in cell_terms if term in known])
    return DesignValidationRead(
        valid=not errors,
        formula=formula,
        resolved_method=resolved_method,
        contrast_label=contrast_label,
        sample_count=len(rows),
        contrast_counts=contrast_counts,
        design_matrix_columns=matrix_columns,
        design_matrix_rank=rank,
        design_cells=cells,
        errors=errors,
        warnings=warnings,
    )


def _read_bundle_metadata(bundle: bytes) -> list[dict[str, str]]:
    with tarfile.open(fileobj=BytesIO(bundle), mode="r:gz") as archive:
        manifest_member = archive.getmember("expression_bundle/bundle_manifest.json")
        manifest_source = archive.extractfile(manifest_member)
        if manifest_source is None:
            raise ValueError("Expression Bundle manifest cannot be read.")
        manifest = json.load(manifest_source)
        relative_path = str(manifest["sample_metadata"])
        if relative_path.startswith("/") or ".." in relative_path.split("/"):
            raise ValueError("Expression Bundle metadata path is unsafe.")
        metadata_member = archive.getmember(f"expression_bundle/{relative_path}")
        metadata_source = archive.extractfile(metadata_member)
        if metadata_source is None:
            raise ValueError("Expression Bundle sample metadata cannot be read.")
        with TextIOWrapper(metadata_source, encoding="utf-8", newline="") as text:
            reader = csv.DictReader(text, delimiter="\t")
            if reader.fieldnames is None or "sample_id" not in reader.fieldnames:
                raise ValueError("Expression Bundle metadata must contain sample_id.")
            rows = [{str(key): str(value) for key, value in row.items()} for row in reader]
    if not rows:
        raise ValueError("Expression Bundle contains no sample metadata rows.")
    return rows


def _variable_kind(values: list[str]) -> Literal["categorical", "numeric"]:
    if not values:
        return "categorical"
    try:
        [float(value) for value in values]
    except ValueError:
        return "categorical"
    return "numeric"


def _resolve_method(assay: str, requested: str, errors: list[str]) -> str:
    if assay == "raw_counts":
        allowed = {"deseq2", "edger_ql", "limma_voom"}
        resolved = "deseq2" if requested == "auto" else requested
    else:
        allowed = {"limma"}
        resolved = "limma" if requested == "auto" else requested
    if resolved not in allowed:
        errors.append(
            f"Method '{resolved}' is incompatible with assay '{assay}'. "
            f"Allowed method(s): {', '.join(sorted(allowed))}."
        )
    return resolved


def _formula(terms: list[str], interactions: list[tuple[str, str]]) -> str:
    interaction_variables = {value for pair in interactions for value in pair}
    components = [term for term in terms if term not in interaction_variables]
    components.extend(f"{left} * {right}" for left, right in interactions)
    return "~ " + " + ".join(components)


def _encode_term(
    name: str,
    values: list[str],
    kind: Literal["categorical", "numeric"],
    requested_reference: str | None,
    errors: list[str],
) -> tuple[list[str], np.ndarray[tuple[int, int], np.dtype[np.float64]]]:
    if kind == "numeric":
        numbers = np.asarray([float(value) for value in values], dtype=np.float64)
        return [name], (numbers - np.mean(numbers)).reshape(-1, 1)
    levels = sorted(set(values))
    reference = requested_reference or levels[0]
    if reference not in levels:
        errors.append(f"Reference level '{reference}' is absent from '{name}'.")
        reference = levels[0]
    encoded_levels = [level for level in levels if level != reference]
    columns = np.column_stack(
        [
            np.asarray([value == level for value in values], dtype=np.float64)
            for level in encoded_levels
        ]
    )
    return [f"{name}[{level}]" for level in encoded_levels], columns


def _design_cells(rows: list[dict[str, str]], terms: list[str]) -> list[DesignCellRead]:
    categorical_terms = [
        term for term in terms if _variable_kind([row[term] for row in rows]) == "categorical"
    ]
    if not categorical_terms:
        return []
    counts = Counter(tuple(row[term] for term in categorical_terms) for row in rows)
    return [
        DesignCellRead(
            values=dict(zip(categorical_terms, values, strict=True)), sample_count=count
        )
        for values, count in sorted(counts.items())
    ]
