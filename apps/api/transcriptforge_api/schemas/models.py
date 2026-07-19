"""Classifier model registry and immutable lock contracts."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    analysis_id: str
    run_id: str
    model_name: str
    algorithm: str
    outcome_column: str
    metrics_json: dict[str, Any]
    feature_count: int
    status: Literal["CANDIDATE", "REVIEWED", "LOCKED", "RETIRED", "SUPERSEDED"]
    reviewed_at: datetime | None
    reviewed_by: str | None
    locked_at: datetime | None
    locked_by: str | None
    retired_at: datetime | None
    parent_model_id: str | None
    model_manifest_sha256: str | None
    model_package_sha256: str | None
    feature_schema_sha256: str | None
    preprocessing_sha256: str | None
    model_object_sha256: str | None
    threshold_sha256: str | None
    training_dataset_refs_json: list[dict[str, Any]]
    validation_dataset_refs_json: list[dict[str, Any]]
    container_digest: str | None
    inference_test_status: str
    created_at: datetime


class ModelDecisionRequest(BaseModel):
    rationale: str = Field(min_length=1, max_length=10_000)


class ModelIntegrityRead(BaseModel):
    model_id: str
    valid: bool
    checks: dict[str, bool]
    errors: list[str]


class ModelLockReadinessRead(BaseModel):
    model_id: str
    ready: bool
    checks: dict[str, bool]
    blockers: list[str]
    warnings: list[str]
