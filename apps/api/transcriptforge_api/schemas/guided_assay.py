"""Typed API contracts for question-first assay development."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from transcriptforge_api.models.enums import (
    AssayLifecycleStage,
    AssayReadinessStatus,
    QuestionSource,
    RecommendationRequirement,
    RecommendationStatus,
)


class AssayProjectCreate(BaseModel):
    project_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=200)
    proposed_purpose: str | None = Field(default=None, max_length=10_000)
    specimen_type: str | None = Field(default=None, max_length=200)
    biological_context: str | None = Field(default=None, max_length=10_000)
    proposed_output: str | None = Field(default=None, max_length=500)
    current_stage: AssayLifecycleStage = AssayLifecycleStage.DEFINE
    assay_version: str | None = Field(default=None, max_length=200)


class AssayProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    proposed_purpose: str | None = Field(default=None, max_length=10_000)
    specimen_type: str | None = Field(default=None, max_length=200)
    biological_context: str | None = Field(default=None, max_length=10_000)
    proposed_output: str | None = Field(default=None, max_length=500)
    assay_version: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def require_change(self) -> "AssayProjectUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one assay-project field must be supplied.")
        return self


class AssayProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    proposed_purpose: str | None
    specimen_type: str | None
    biological_context: str | None
    proposed_output: str | None
    current_stage: AssayLifecycleStage
    readiness_status: AssayReadinessStatus
    active_question_id: str | None
    assay_version: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class QuestionCatalogEntry(BaseModel):
    key: str
    question: str
    stage: AssayLifecycleStage
    experiment_type: str | None = None
    analysis_type: str | None = None
    study_type: str | None = None
    required_inputs: list[str]
    required_metadata: list[str]
    recommended_endpoints: list[str]
    design_checks: list[str]
    possible_next_actions: list[str]


class QuestionCatalog(BaseModel):
    schema_version: Literal["1.0.0"]
    catalog_version: str
    questions: list[QuestionCatalogEntry]


class ScientificQuestionCreate(BaseModel):
    question_key: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    formal_question: str = Field(min_length=1, max_length=10_000)
    source: QuestionSource = QuestionSource.USER_SELECTED


class ScientificQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assay_project_id: str
    question_key: str
    plain_language_question: str
    formal_question: str
    stage: AssayLifecycleStage
    status: Literal["OPEN", "RESOLVED", "SUPERSEDED"]
    source: QuestionSource
    created_at: datetime
    resolved_at: datetime | None
    resolution_summary: str | None


class ReadinessItem(BaseModel):
    rule_id: str
    facts: dict[str, Any]
    conclusion: str
    severity: Literal["INFO", "WARNING", "BLOCKER"]
    suggested_action: str
    assumptions: list[str]
    documentation_url: str


class ReadinessResult(BaseModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    stage: AssayLifecycleStage
    status: AssayReadinessStatus
    evaluated_at: datetime
    ready_items: list[ReadinessItem]
    missing_items: list[ReadinessItem]
    blockers: list[ReadinessItem]
    warnings: list[ReadinessItem]
    recommended_action_ids: list[str]
    alternative_action_ids: list[str]
    not_recommended_action_ids: list[str]


class RecommendationRead(BaseModel):
    id: str
    assay_project_id: str
    source_type: str
    source_id: str
    rule_id: str
    recommendation_type: str
    title: str
    summary: str
    why: str
    what_it_resolves: str
    stage: AssayLifecycleStage
    priority: int
    requirement_level: RecommendationRequirement
    status: RecommendationStatus
    required_inputs: list[str]
    expected_output: str
    proposed_action: dict[str, Any]
    evidence_refs: list[dict[str, Any]]
    assumptions: list[str]
    limitations: list[str]
    alternative_action_ids: list[str]
    scientist_decision_required: Literal[True] = True
    created_at: datetime
    resolved_at: datetime | None


class RecommendationDecision(BaseModel):
    rationale: str = Field(min_length=1, max_length=10_000)
    modified_action: dict[str, Any] | None = None


class RecommendationResolutionResponse(BaseModel):
    decision: "DecisionRead"
    replacement_recommendation: RecommendationRead | None
    action_launched: Literal[False] = False


class DecisionCreate(BaseModel):
    source_type: Literal["RECOMMENDATION", "STAGE", "QUESTION", "EXPERIMENT", "MODEL", "STUDY"]
    source_id: str = Field(min_length=1)
    stage: AssayLifecycleStage
    decision_key: str = Field(min_length=1, max_length=100)
    decision: str = Field(min_length=1, max_length=10_000)
    rationale: str = Field(min_length=1, max_length=10_000)
    selected_option: str = Field(min_length=1, max_length=100)
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    supersedes_decision_id: str | None = None


class DecisionRead(BaseModel):
    id: str
    assay_project_id: str
    source_type: str
    source_id: str
    stage: AssayLifecycleStage
    decision_key: str
    decision: str
    rationale: str
    selected_option: str
    alternatives: list[dict[str, Any]]
    evidence_refs: list[dict[str, Any]]
    made_by: str
    made_at: datetime
    supersedes_decision_id: str | None


class StageDecisionCreate(BaseModel):
    requested_stage: AssayLifecycleStage
    decision: Literal["ACCEPT", "REJECT", "DEFER"]
    rationale: str = Field(min_length=1, max_length=10_000)


class GuidanceRecomputeResponse(BaseModel):
    readiness: ReadinessResult
    recommendations: list[RecommendationRead]


class GuidanceResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assay_project_id: str
    question_id: str
    analysis_id: str
    run_id: str
    payload_json: dict[str, Any]
    artifact_uri: str
    artifact_sha256: str
    created_at: datetime


class TimelineEvent(BaseModel):
    id: str
    event_type: str
    actor: str
    object_type: str
    object_id: str
    revision: int | None
    hashes: dict[str, str]
    details: dict[str, Any]
    created_at: datetime
