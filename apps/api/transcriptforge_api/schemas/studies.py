"""Post-lock analytical study API contracts."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StudyAssignment(BaseModel):
    measurement_id: str = Field(min_length=1, max_length=300)
    biological_sample_id: str = Field(min_length=1, max_length=300)
    replicate_id: str | None = Field(default=None, min_length=1, max_length=300)
    operator: str | None = Field(default=None, min_length=1, max_length=200)
    run: str | None = Field(default=None, min_length=1, max_length=200)
    reagent_lot: str | None = Field(default=None, min_length=1, max_length=200)
    input_level: float | None = Field(default=None, gt=0)
    quality_metric: float | None = None
    qc_failure: bool = False
    condition: str | None = Field(default=None, min_length=1, max_length=300)
    challenge_type: str | None = Field(default=None, min_length=1, max_length=300)
    subgroup: str | None = Field(default=None, min_length=1, max_length=300)
    instrument: str | None = Field(default=None, max_length=200)
    day: str | None = Field(default=None, max_length=200)
    site: str | None = Field(default=None, max_length=200)
    include: bool = True
    exclusion_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_exclusion_reason(self) -> "StudyAssignment":
        if not self.include and not self.exclusion_reason:
            raise ValueError("Excluded measurements require a reason.")
        return self


class AcceptanceCriterionCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]+$", max_length=100)
    metric: Literal[
        "icc",
        "categorical_agreement",
        "repeatability_sd",
        "reproducibility_sd",
        "mean_absolute_score_difference",
        "call_agreement_to_reference",
        "qc_failure_rate",
        "paired_bias",
        "discordance_rate",
        "profile_correlation",
        "tost_equivalence",
        "mean_challenge_effect",
        "call_change_rate",
    ]
    endpoint: Literal["classifier_score", "predicted_class", "qc_failure"]
    operator: Literal[
        "gt",
        "gte",
        "lt",
        "lte",
        "between",
        "absolute_lte",
        "all_levels",
        "consecutive_levels",
    ]
    threshold: float | list[float]
    rationale: str = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def validate_threshold_shape(self) -> "AcceptanceCriterionCreate":
        if self.operator == "between":
            if (
                not isinstance(self.threshold, list)
                or len(self.threshold) != 2
                or self.threshold[0] > self.threshold[1]
            ):
                raise ValueError("A between criterion requires ordered lower and upper bounds.")
        elif isinstance(self.threshold, list):
            raise ValueError("Only a between criterion accepts a threshold range.")
        return self


class StudyCreate(BaseModel):
    assay_project_id: str
    question_id: str
    model_id: str
    prepared_dataset_id: str
    name: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=10_000)
    study_type: Literal[
        "PRECISION_REPRODUCIBILITY",
        "INPUT_DEGRADATION_LIMIT",
        "PAIRED_BRIDGING",
        "ROBUSTNESS_INTERFERENCE",
    ] = "PRECISION_REPRODUCIBILITY"
    assignments: list[StudyAssignment] = Field(min_length=4)
    factors: list[str] = Field(default_factory=lambda: ["operator", "run", "reagent_lot"])
    criteria: list[AcceptanceCriterionCreate] = Field(min_length=1)
    confidence_level: float = Field(default=0.95, gt=0, lt=1)
    bootstrap_iterations: int = Field(default=2000, ge=200, le=10_000)
    threshold_proximity_band: float = Field(default=0.10, ge=0, le=1)
    reference_level: float | None = Field(default=None, gt=0)
    level_rationale: str | None = Field(default=None, min_length=1, max_length=10_000)
    reference_condition: str | None = Field(default=None, min_length=1, max_length=300)
    comparator_condition: str | None = Field(default=None, min_length=1, max_length=300)
    equivalence_margin: float | None = Field(default=None, gt=0)
    condition_rationale: str | None = Field(default=None, min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def validate_design_declarations(self) -> "StudyCreate":
        allowed = {
            "operator",
            "run",
            "reagent_lot",
            "instrument",
            "day",
            "site",
            "input_level",
            "quality_metric",
            "condition",
            "challenge_type",
            "subgroup",
        }
        if not self.factors or len(self.factors) != len(set(self.factors)):
            raise ValueError("Study factors must be nonempty and unique.")
        unsupported = sorted(set(self.factors) - allowed)
        if unsupported:
            raise ValueError(f"Unsupported study factor(s): {', '.join(unsupported)}.")
        if self.study_type == "PRECISION_REPRODUCIBILITY":
            incomplete = [
                item.measurement_id
                for item in self.assignments
                if item.include
                and (
                    not item.replicate_id
                    or not item.operator
                    or not item.run
                    or not item.reagent_lot
                )
            ]
        elif self.study_type == "INPUT_DEGRADATION_LIMIT":
            if self.reference_level is None or not self.level_rationale:
                raise ValueError(
                    "Input/degradation limit studies require a reference level and rationale."
                )
            incomplete = [
                item.measurement_id
                for item in self.assignments
                if item.include and (item.input_level is None or not item.run)
            ]
        elif self.study_type == "PAIRED_BRIDGING":
            if (
                not self.reference_condition
                or not self.comparator_condition
                or self.reference_condition == self.comparator_condition
                or self.equivalence_margin is None
                or not self.condition_rationale
            ):
                raise ValueError(
                    "Paired bridging requires distinct conditions, an equivalence margin, "
                    "and a scientific rationale."
                )
            incomplete = [
                item.measurement_id
                for item in self.assignments
                if item.include and (not item.condition or not item.run)
            ]
            if not any(
                criterion.metric in {"paired_bias", "tost_equivalence"}
                for criterion in self.criteria
            ):
                raise ValueError(
                    "Paired bridging requires a bias/equivalence criterion; correlation alone "
                    "cannot pass equivalence."
                )
        else:
            if (
                not self.reference_condition
                or not self.comparator_condition
                or self.reference_condition == self.comparator_condition
                or self.equivalence_margin is None
                or not self.condition_rationale
            ):
                raise ValueError(
                    "Robustness/interference studies require distinct reference and challenge "
                    "conditions, a maximum effect margin, and a scientific rationale."
                )
            incomplete = [
                item.measurement_id
                for item in self.assignments
                if item.include and (not item.condition or not item.challenge_type or not item.run)
            ]
            if not any(
                criterion.metric in {"mean_challenge_effect", "call_change_rate"}
                for criterion in self.criteria
            ):
                raise ValueError(
                    "Robustness/interference requires a challenge-effect or call-change criterion."
                )
        if incomplete:
            raise ValueError(
                "Included assignments are missing template-required fields: "
                + ", ".join(incomplete)
            )
        keys = [criterion.key for criterion in self.criteria]
        if len(keys) != len(set(keys)):
            raise ValueError("Acceptance-criterion keys must be unique.")
        return self


class StudyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    objective: str | None = Field(default=None, min_length=1, max_length=10_000)
    assignments: list[StudyAssignment] | None = Field(default=None, min_length=4)
    factors: list[str] | None = None
    criteria: list[AcceptanceCriterionCreate] | None = Field(default=None, min_length=1)
    confidence_level: float | None = Field(default=None, gt=0, lt=1)
    bootstrap_iterations: int | None = Field(default=None, ge=200, le=10_000)
    threshold_proximity_band: float | None = Field(default=None, ge=0, le=1)
    reference_level: float | None = Field(default=None, gt=0)
    level_rationale: str | None = Field(default=None, min_length=1, max_length=10_000)
    reference_condition: str | None = Field(default=None, min_length=1, max_length=300)
    comparator_condition: str | None = Field(default=None, min_length=1, max_length=300)
    equivalence_margin: float | None = Field(default=None, gt=0)
    condition_rationale: str | None = Field(default=None, min_length=1, max_length=10_000)


class StudyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assay_project_id: str
    question_id: str
    model_id: str
    prepared_dataset_id: str
    parent_study_id: str | None
    name: str
    study_type: str
    objective: str
    status: str
    study_spec_json: dict[str, Any]
    assignments_json: list[dict[str, Any]]
    criteria_json: list[dict[str, Any]]
    design_validation_json: dict[str, Any] | None
    study_spec_uri: str | None
    study_spec_sha256: str | None
    assignments_uri: str | None
    assignments_sha256: str | None
    validation_bundle_uri: str | None
    current_revision: int
    created_by: str
    created_at: datetime
    updated_at: datetime
    locked_at: datetime | None
    completed_at: datetime | None


class StudyResultsRead(BaseModel):
    study_id: str
    status: str
    run_id: str | None
    summary: dict[str, Any] | None
    artifacts: list[dict[str, Any]]


class StudyRunRead(BaseModel):
    study: StudyRead
    run_id: str
    run_state: str


class LockedModelOption(BaseModel):
    id: str
    name: str
    algorithm: str
    expected_assay: str
    feature_count: int
    manifest_sha256: str


class StudyDatasetOption(BaseModel):
    id: str
    dataset_name: str
    version: int
    sample_count: int
    feature_count: int
    assays: list[str]
    qc_status: str


class StudyInputOptions(BaseModel):
    locked_models: list[LockedModelOption]
    prepared_datasets: list[StudyDatasetOption]
