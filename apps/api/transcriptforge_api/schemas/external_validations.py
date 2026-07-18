"""Contracts for immutable classifier external-validation studies."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DevelopmentClassifierSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_count: int = Field(gt=0)
    input_feature_count: int = Field(gt=0)
    selected_feature_count: int = Field(gt=0)
    roc_auc: float = Field(ge=0, le=1)
    roc_auc_lower: float = Field(ge=0, le=1)
    roc_auc_upper: float = Field(ge=0, le=1)
    pr_auc: float = Field(ge=0, le=1)
    permutation_p_value: float | None = Field(default=None, ge=0, le=1)


class ClassifierExternalValidationImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    development_summary: DevelopmentClassifierSummary


class ClassifierExternalValidationArtifactRead(BaseModel):
    name: str
    title: str
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str


class ClassifierExternalValidationRead(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None
    development_accession: str
    external_accession: str
    protocol_id: str
    status: str
    development_summary: dict[str, Any]
    prediction_summary: dict[str, Any] | None
    protocol: dict[str, Any]
    result: dict[str, Any]
    artifacts: list[ClassifierExternalValidationArtifactRead]
    created_at: datetime
