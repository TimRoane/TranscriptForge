"""API contracts for pre-lock Development Experiments."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

FactorName = Literal[
    "condition",
    "extraction_method",
    "library_method",
    "input_ng",
    "dv200",
    "operator",
    "reagent_lot",
    "instrument",
    "sequencing_depth",
]


def _default_factor_names() -> list[FactorName]:
    return ["condition", "input_ng"]


class ExperimentAssignment(BaseModel):
    measurement_id: str = Field(min_length=1, max_length=300)
    biological_sample_id: str = Field(min_length=1, max_length=300)
    prepared_dataset_id: str = Field(min_length=1)
    include: bool = True
    exclusion_reason: str | None = Field(default=None, max_length=2000)
    replicate_id: str | None = Field(default=None, max_length=300)
    pair_id: str | None = Field(default=None, max_length=300)
    input_ng: float | None = Field(default=None, gt=0)
    dv200: float | None = Field(default=None, ge=0, le=100)
    sequencing_run: str | None = Field(default=None, min_length=1, max_length=300)
    condition: str | None = Field(default=None, min_length=1, max_length=300)
    run: str | None = Field(default=None, min_length=1, max_length=300)
    quality_metric: float | None = None
    operator: str | None = Field(default=None, max_length=300)
    reagent_lot: str | None = Field(default=None, max_length=300)
    instrument: str | None = Field(default=None, max_length=300)
    processing_order: int | None = Field(default=None, ge=1)
    extraction_method: str | None = Field(default=None, min_length=1, max_length=300)
    library_method: str | None = Field(default=None, min_length=1, max_length=300)
    sequencing_depth: float | None = Field(default=None, gt=0)
    specimen_group: str | None = Field(default=None, min_length=1, max_length=300)
    technical_failure: bool = False

    @model_validator(mode="after")
    def require_exclusion_reason(self) -> "ExperimentAssignment":
        if not self.include and not (self.exclusion_reason or "").strip():
            raise ValueError("Excluded measurements require an exclusion reason.")
        return self


class ExperimentCreate(BaseModel):
    assay_project_id: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    prepared_dataset_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=10_000)
    experiment_type: Literal[
        "INPUT_DEGRADATION_EXPLORATION",
        "PAIRED_CONDITION_COMPARISON",
        "MULTIFACTOR_OPTIMIZATION",
        "TECHNICAL_FEASIBILITY",
    ]
    mode: Literal["PLAN_FIRST", "ANALYZE_EXISTING"]
    reference_level: float | None = Field(default=None, gt=0)
    reference_condition: str | None = Field(default=None, min_length=1, max_length=300)
    comparator_condition: str | None = Field(default=None, min_length=1, max_length=300)
    assay: str = Field(default="log_expression", min_length=1, max_length=100)
    primary_endpoints: list[str] = Field(
        default_factory=lambda: [
            "expression_profile_correlation_to_reference",
            "detected_genes",
        ],
        min_length=1,
    )
    secondary_endpoints: list[str] = Field(default_factory=lambda: ["mean_expression"])
    declared_questions: list[str] = Field(min_length=1)
    reference_level_rationale: str | None = Field(default=None, min_length=1, max_length=10_000)
    condition_contrast_rationale: str | None = Field(default=None, min_length=1, max_length=10_000)
    endpoint_rationale: str = Field(min_length=1, max_length=10_000)
    assignments: list[ExperimentAssignment] = Field(min_length=1)
    factor_names: list[FactorName] = Field(
        default_factory=_default_factor_names, min_length=2, max_length=3
    )
    interactions: list[str] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def validate_template_fields(self) -> "ExperimentCreate":
        if self.experiment_type == "TECHNICAL_FEASIBILITY":
            incomplete = [
                row.measurement_id
                for row in self.assignments
                if row.include and not (row.run or row.sequencing_run)
            ]
        elif self.experiment_type == "INPUT_DEGRADATION_EXPLORATION":
            if self.reference_level is None or not self.reference_level_rationale:
                raise ValueError(
                    "Input/degradation experiments require a reference level and rationale."
                )
            incomplete = [
                row.measurement_id
                for row in self.assignments
                if row.include
                and (row.input_ng is None or row.dv200 is None or row.sequencing_run is None)
            ]
        elif self.experiment_type == "PAIRED_CONDITION_COMPARISON":
            if (
                not self.reference_condition
                or not self.comparator_condition
                or self.reference_condition == self.comparator_condition
                or not self.condition_contrast_rationale
            ):
                raise ValueError(
                    "Paired-condition experiments require distinct reference/comparator "
                    "conditions and a contrast rationale."
                )
            incomplete = [
                row.measurement_id
                for row in self.assignments
                if row.include and (row.condition is None or row.run is None)
            ]
        else:
            if len(self.factor_names) != len(set(self.factor_names)):
                raise ValueError("Multifactor factors must be unique.")
            allowed_interactions = {
                ":".join(sorted((left, right)))
                for index, left in enumerate(self.factor_names)
                for right in self.factor_names[index + 1 :]
            }
            normalized = [":".join(sorted(value.split(":"))) for value in self.interactions]
            if any(value not in allowed_interactions for value in normalized):
                raise ValueError("Interactions must name two declared factors.")
            incomplete = [
                row.measurement_id
                for row in self.assignments
                if row.include
                and (
                    not row.run or any(getattr(row, factor) is None for factor in self.factor_names)
                )
            ]
        if incomplete:
            raise ValueError(
                "Included assignments are missing template-required fields: "
                + ", ".join(incomplete)
            )
        return self


class ExperimentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    objective: str | None = Field(default=None, min_length=1, max_length=10_000)
    reference_level: float | None = Field(default=None, gt=0)
    reference_condition: str | None = Field(default=None, min_length=1, max_length=300)
    comparator_condition: str | None = Field(default=None, min_length=1, max_length=300)
    primary_endpoints: list[str] | None = Field(default=None, min_length=1)
    secondary_endpoints: list[str] | None = None
    declared_questions: list[str] | None = Field(default=None, min_length=1)
    reference_level_rationale: str | None = Field(default=None, min_length=1, max_length=10_000)
    condition_contrast_rationale: str | None = Field(default=None, min_length=1, max_length=10_000)
    endpoint_rationale: str | None = Field(default=None, min_length=1, max_length=10_000)
    assignments: list[ExperimentAssignment] | None = Field(default=None, min_length=1)
    factor_names: list[str] | None = Field(default=None, min_length=2, max_length=3)
    interactions: list[str] | None = Field(default=None, max_length=2)

    @model_validator(mode="after")
    def require_change(self) -> "ExperimentUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one experiment field must be supplied.")
        return self


class ExperimentRead(BaseModel):
    id: str
    assay_project_id: str
    question_id: str
    prepared_dataset_id: str
    parent_experiment_id: str | None
    name: str
    experiment_type: Literal[
        "INPUT_DEGRADATION_EXPLORATION",
        "PAIRED_CONDITION_COMPARISON",
        "MULTIFACTOR_OPTIMIZATION",
        "TECHNICAL_FEASIBILITY",
    ]
    objective: str
    mode: Literal["PLAN_FIRST", "ANALYZE_EXISTING"]
    status: Literal[
        "DRAFT",
        "DESIGN_VALID",
        "DESIGN_INVALID",
        "LOCKED_FOR_EXECUTION",
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        "SUPERSEDED",
    ]
    experiment_spec: dict[str, Any]
    experiment_spec_uri: str | None
    experiment_spec_sha256: str | None
    assignments: list[ExperimentAssignment]
    assignments_uri: str | None
    assignments_sha256: str | None
    design_validation: dict[str, Any] | None
    development_bundle_uri: str | None
    current_revision: int
    created_by: str
    created_at: datetime
    updated_at: datetime
    locked_at: datetime | None
    completed_at: datetime | None


class ExperimentRunResponse(BaseModel):
    experiment: ExperimentRead
    run_id: str
    run_state: Literal["QUEUED"]


class ExperimentResultResponse(BaseModel):
    experiment_id: str
    status: str
    run_id: str | None
    decision_summary: dict[str, Any] | None
    recommendations: dict[str, Any] | None
    artifacts: list[dict[str, Any]]


class ExperimentInputOption(BaseModel):
    prepared_dataset_id: str
    dataset_id: str
    dataset_name: str
    prepared_version: int
    sample_count: int
    feature_count: int
    assays: list[str]
    qc_status: str


class ExperimentDesignOptions(BaseModel):
    prepared_dataset_id: str
    sample_count: int
    assays: list[str]
    measurement_ids: list[str]
    metadata_columns: list[str]
    metadata_rows: list[dict[str, str]]
