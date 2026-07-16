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
