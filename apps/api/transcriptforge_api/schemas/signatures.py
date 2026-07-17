"""Candidate gene signature draft API contracts."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from transcriptforge_api.schemas.runs import DifferentialExpressionSort, SortDirection

RESEARCH_USE_WARNING = (
    "Candidate genes selected from this differential-expression run are not independently "
    "validated and do not constitute a diagnostic or clinically validated signature."
)


class SignatureSelection(BaseModel):
    mode: Literal["manual"] = "manual"
    search: str | None = Field(default=None, max_length=200)
    fdr_max: float | None = Field(default=None, ge=0, le=1)
    absolute_log2_fold_change_min: float | None = Field(default=None, ge=0)
    significant_only: bool = False
    sort_by: DifferentialExpressionSort = "adjusted_p_value"
    direction: SortDirection = "asc"


class GeneSignatureCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    feature_ids: list[str] = Field(min_length=1, max_length=500)
    selection: SignatureSelection = Field(default_factory=SignatureSelection)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Signature name cannot be blank.")
        return normalized

    @field_validator("feature_ids")
    @classmethod
    def validate_features(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 200 for value in normalized):
            raise ValueError("Feature identifiers must contain 1 to 200 characters.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Feature identifiers must be unique within a signature draft.")
        return normalized


class GeneSignatureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    prepared_dataset_id: str
    source_analysis_id: str
    source_run_id: str
    name: str
    description: str | None
    status: Literal["draft"]
    feature_ids: list[str]
    feature_snapshot_json: list[dict[str, Any]]
    selection_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    research_use_warning: str = RESEARCH_USE_WARNING


class SignatureDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    description: str | None
    definition_format: Literal["gene_list", "gmt"]
    identifier_type: Literal["ensembl_gene_id", "gene_symbol", "entrez_id"]
    original_name: str
    source_sha256: str
    source_size_bytes: int
    manifest_sha256: str
    set_count: int
    requested_identifier_count: int
    unique_identifier_count: int
    duplicate_identifier_count: int
    weighted: bool
    created_at: datetime
    updated_at: datetime


class SignatureMappingSetRead(BaseModel):
    signature_id: str
    name: str
    requested_identifier_count: int
    unique_identifier_count: int
    mapped_identifier_count: int
    missing_identifier_count: int
    ambiguous_identifier_count: int
    duplicate_identifier_count: int
    mapping_coverage: float
    mapped_entries: list[dict[str, str | float]]
    mapped_feature_ids: list[str]
    missing_identifiers: list[str]
    ambiguous_identifiers: list[str]


class SignatureMappingRead(BaseModel):
    schema_version: Literal["1.0.0"]
    signature_definition_id: str
    prepared_dataset_id: str
    signature_definition_sha256: str
    expression_bundle_sha256: str
    identifier_type: Literal["ensembl_gene_id", "gene_symbol", "entrez_id"]
    strip_ensembl_version: bool
    set_count: int
    requested_identifier_count: int
    unique_identifier_count: int
    mapped_identifier_count: int
    missing_identifier_count: int
    ambiguous_identifier_count: int
    duplicate_identifier_count: int
    mapping_coverage: float
    sets: list[SignatureMappingSetRead]


class SignatureMappingRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    signature_definition_id: str
    prepared_dataset_id: str
    report_sha256: str
    missing_sha256: str
    ambiguous_sha256: str
    requested_identifier_count: int
    unique_identifier_count: int
    mapped_identifier_count: int
    missing_identifier_count: int
    ambiguous_identifier_count: int
    duplicate_identifier_count: int
    mapping_coverage: float
    report_json: SignatureMappingRead
    created_at: datetime
    updated_at: datetime
