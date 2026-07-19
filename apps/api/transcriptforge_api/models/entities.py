"""Core persistence entities for datasets, analyses, and immutable runs."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from transcriptforge_api.models.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    utc_now,
)


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Top-level namespace for datasets, analyses, and models."""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[str] = mapped_column(String(200), default="local-user", index=True)

    datasets: Mapped[list["Dataset"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    analyses: Mapped[list["Analysis"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    gene_signatures: Mapped[list["GeneSignature"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    signature_definitions: Mapped[list["SignatureDefinition"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    classifier_external_validations: Mapped[list["ClassifierExternalValidation"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    assay_development_projects: Mapped[list["AssayDevelopmentProject"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )


class Dataset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """User-registered source data before preparation."""

    __tablename__ = "datasets"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    modality: Mapped[str] = mapped_column(String(40))
    source_kind: Mapped[str] = mapped_column(String(40))
    organism: Mapped[str] = mapped_column(String(100), default="Homo sapiens")
    genome_build: Mapped[str | None] = mapped_column(String(100))
    annotation_release: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(40), default="draft")

    project: Mapped[Project] = relationship(back_populates="datasets")
    files: Mapped[list["DatasetFile"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", passive_deletes=True
    )
    prepared_versions: Mapped[list["PreparedDataset"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", passive_deletes=True
    )


class DatasetFile(UUIDPrimaryKeyMixin, Base):
    """Immutable uploaded or registered object belonging to a dataset."""

    __tablename__ = "dataset_files"

    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(50), index=True)
    original_name: Mapped[str] = mapped_column(String(500))
    storage_uri: Mapped[str] = mapped_column(String(2000), unique=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    dataset: Mapped[Dataset] = relationship(back_populates="files")


class PreparedDataset(UUIDPrimaryKeyMixin, Base):
    """One immutable version of a canonical Expression Bundle."""

    __tablename__ = "prepared_datasets"
    __table_args__ = (Index("uq_prepared_dataset_version", "dataset_id", "version", unique=True),)

    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int]
    preparation_run_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "runs.id",
            name="fk_prepared_datasets_preparation_run_id_runs",
            use_alter=True,
            ondelete="SET NULL",
        ),
        unique=True,
    )
    bundle_uri: Mapped[str] = mapped_column(String(2000), unique=True)
    bundle_manifest_uri: Mapped[str] = mapped_column(String(2000), unique=True)
    value_types_available: Mapped[list[str]] = mapped_column(JSON, default=list)
    sample_count: Mapped[int]
    feature_count: Mapped[int]
    qc_status: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    dataset: Mapped[Dataset] = relationship(back_populates="prepared_versions")
    analyses: Mapped[list["Analysis"]] = relationship(back_populates="prepared_dataset")


class Analysis(UUIDPrimaryKeyMixin, Base):
    """Saved, cloneable analysis configuration."""

    __tablename__ = "analyses"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    prepared_dataset_id: Mapped[str] = mapped_column(
        ForeignKey("prepared_datasets.id", ondelete="CASCADE"), index=True
    )
    assay_project_id: Mapped[str | None] = mapped_column(
        ForeignKey("assay_development_projects.id", ondelete="CASCADE"), index=True
    )
    scientific_question_id: Mapped[str | None] = mapped_column(
        ForeignKey("scientific_questions.id", ondelete="SET NULL"), index=True
    )
    analysis_type: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    configuration_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    project: Mapped[Project] = relationship(back_populates="analyses")
    prepared_dataset: Mapped[PreparedDataset] = relationship(back_populates="analyses")


class Run(UUIDPrimaryKeyMixin, Base):
    """Durable execution state and immutable run locations."""

    __tablename__ = "runs"

    run_type: Mapped[str] = mapped_column(String(40), index=True)
    dataset_id: Mapped[str | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    prepared_dataset_id: Mapped[str | None] = mapped_column(
        ForeignKey("prepared_datasets.id", ondelete="CASCADE"), index=True
    )
    analysis_id: Mapped[str | None] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    experiment_id: Mapped[str | None] = mapped_column(
        ForeignKey("experiment_plans.id", ondelete="CASCADE"), index=True
    )
    study_id: Mapped[str | None] = mapped_column(
        ForeignKey("analytical_studies.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[str] = mapped_column(String(30), default="CREATED", index=True)
    profile: Mapped[str] = mapped_column(String(50), default="docker")
    params_uri: Mapped[str] = mapped_column(String(2000))
    output_uri: Mapped[str] = mapped_column(String(2000))
    work_uri: Mapped[str] = mapped_column(String(2000))
    nextflow_session_id: Mapped[str | None] = mapped_column(String(200))
    nextflow_run_name: Mapped[str | None] = mapped_column(String(200))
    exit_code: Mapped[int | None]
    error_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    model_records: Mapped[list["ModelRecord"]] = relationship(back_populates="run")
    experiment: Mapped["ExperimentPlan | None"] = relationship(back_populates="runs")
    study: Mapped["AnalyticalStudy | None"] = relationship(back_populates="runs")


class Artifact(UUIDPrimaryKeyMixin, Base):
    """Indexed user-visible file published by a run."""

    __tablename__ = "artifacts"

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(300))
    relative_path: Mapped[str] = mapped_column(String(2000))
    storage_uri: Mapped[str] = mapped_column(String(2000), unique=True)
    mime_type: Mapped[str] = mapped_column(String(200))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    display_order: Mapped[int] = mapped_column(default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    run: Mapped[Run] = relationship(back_populates="artifacts")


class ModelRecord(UUIDPrimaryKeyMixin, Base):
    """Registry entry for a frozen research model and model card."""

    __tablename__ = "model_records"

    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    model_name: Mapped[str] = mapped_column(String(200))
    algorithm: Mapped[str] = mapped_column(String(100))
    outcome_column: Mapped[str] = mapped_column(String(200))
    model_uri: Mapped[str] = mapped_column(String(2000), unique=True)
    model_card_uri: Mapped[str] = mapped_column(String(2000), unique=True)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    feature_count: Mapped[int]
    status: Mapped[str] = mapped_column(String(30), default="CANDIDATE", index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(200))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(200))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parent_model_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_records.id", ondelete="SET NULL"), index=True
    )
    model_manifest_uri: Mapped[str | None] = mapped_column(String(2000), unique=True)
    model_manifest_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    model_package_uri: Mapped[str | None] = mapped_column(String(2000), unique=True)
    model_package_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    feature_schema_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    preprocessing_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    model_object_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    threshold_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    training_dataset_refs_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    validation_dataset_refs_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    container_digest: Mapped[str | None] = mapped_column(String(80))
    inference_test_status: Mapped[str] = mapped_column(String(30), default="NOT_RUN")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    run: Mapped[Run] = relationship(back_populates="model_records")


class ClassifierExternalValidation(UUIDPrimaryKeyMixin, Base):
    """Immutable one-shot evaluation of a locked classifier on an external cohort."""

    __tablename__ = "classifier_external_validations"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    development_accession: Mapped[str] = mapped_column(String(40), index=True)
    external_accession: Mapped[str] = mapped_column(String(40), index=True)
    protocol_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50), index=True)
    development_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    prediction_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    protocol_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    artifacts_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    project: Mapped[Project] = relationship(back_populates="classifier_external_validations")


class GeneSignature(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Provenance-frozen candidate gene set awaiting independent validation."""

    __tablename__ = "gene_signatures"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    prepared_dataset_id: Mapped[str] = mapped_column(
        ForeignKey("prepared_datasets.id", ondelete="CASCADE"), index=True
    )
    source_analysis_id: Mapped[str] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    source_run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    feature_ids: Mapped[list[str]] = mapped_column(JSON)
    feature_snapshot_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    selection_json: Mapped[dict[str, Any]] = mapped_column(JSON)

    project: Mapped[Project] = relationship(back_populates="gene_signatures")


class SignatureDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable uploaded signature definition for cross-dataset evaluation."""

    __tablename__ = "signature_definitions"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    definition_format: Mapped[str] = mapped_column(String(40))
    identifier_type: Mapped[str] = mapped_column(String(40))
    original_name: Mapped[str] = mapped_column(String(500))
    source_uri: Mapped[str] = mapped_column(String(2000), unique=True)
    source_sha256: Mapped[str] = mapped_column(String(64), index=True)
    source_size_bytes: Mapped[int] = mapped_column(BigInteger)
    manifest_uri: Mapped[str] = mapped_column(String(2000), unique=True)
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    set_count: Mapped[int]
    requested_identifier_count: Mapped[int]
    unique_identifier_count: Mapped[int]
    duplicate_identifier_count: Mapped[int]
    weighted: Mapped[bool]
    definition_json: Mapped[dict[str, Any]] = mapped_column(JSON)

    project: Mapped[Project] = relationship(back_populates="signature_definitions")


class SignatureMapping(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable mapping of one signature definition to one prepared dataset."""

    __tablename__ = "signature_mappings"
    __table_args__ = (
        Index(
            "uq_signature_mapping_definition_prepared",
            "signature_definition_id",
            "prepared_dataset_id",
            unique=True,
        ),
    )

    signature_definition_id: Mapped[str] = mapped_column(
        ForeignKey("signature_definitions.id", ondelete="CASCADE"), index=True
    )
    prepared_dataset_id: Mapped[str] = mapped_column(
        ForeignKey("prepared_datasets.id", ondelete="CASCADE"), index=True
    )
    report_uri: Mapped[str] = mapped_column(String(2000), unique=True)
    report_sha256: Mapped[str] = mapped_column(String(64))
    missing_uri: Mapped[str] = mapped_column(String(2000), unique=True)
    missing_sha256: Mapped[str] = mapped_column(String(64))
    ambiguous_uri: Mapped[str] = mapped_column(String(2000), unique=True)
    ambiguous_sha256: Mapped[str] = mapped_column(String(64))
    requested_identifier_count: Mapped[int]
    unique_identifier_count: Mapped[int]
    mapped_identifier_count: Mapped[int]
    missing_identifier_count: Mapped[int]
    ambiguous_identifier_count: Mapped[int]
    duplicate_identifier_count: Mapped[int]
    mapping_coverage: Mapped[float]
    report_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class AssayDevelopmentProject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Stage-aware assay-development workspace linked to a base project."""

    __tablename__ = "assay_development_projects"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), index=True)
    proposed_purpose: Mapped[str | None] = mapped_column(Text)
    specimen_type: Mapped[str | None] = mapped_column(String(200))
    biological_context: Mapped[str | None] = mapped_column(Text)
    proposed_output: Mapped[str | None] = mapped_column(String(500))
    current_stage: Mapped[str] = mapped_column(String(40), default="DEFINE", index=True)
    readiness_status: Mapped[str] = mapped_column(String(50), default="NOT_ASSESSED", index=True)
    active_question_id: Mapped[str | None] = mapped_column(String(36), index=True)
    assay_version: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[str] = mapped_column(String(200), default="local-user")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(back_populates="assay_development_projects")
    questions: Mapped[list["ScientificQuestion"]] = relationship(
        back_populates="assay_project", cascade="all, delete-orphan", passive_deletes=True
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="assay_project", cascade="all, delete-orphan", passive_deletes=True
    )
    decisions: Mapped[list["DecisionRecord"]] = relationship(
        back_populates="assay_project", cascade="all, delete-orphan", passive_deletes=True
    )
    audit_events: Mapped[list["AssayAuditEvent"]] = relationship(
        back_populates="assay_project", cascade="all, delete-orphan", passive_deletes=True
    )
    experiments: Mapped[list["ExperimentPlan"]] = relationship(
        back_populates="assay_project", cascade="all, delete-orphan", passive_deletes=True
    )
    guidance_results: Mapped[list["GuidanceResult"]] = relationship(
        back_populates="assay_project", cascade="all, delete-orphan", passive_deletes=True
    )
    studies: Mapped[list["AnalyticalStudy"]] = relationship(
        back_populates="assay_project", cascade="all, delete-orphan", passive_deletes=True
    )


class ScientificQuestion(UUIDPrimaryKeyMixin, Base):
    """Versioned plain-language question currently informing an assay decision."""

    __tablename__ = "scientific_questions"

    assay_project_id: Mapped[str] = mapped_column(
        ForeignKey("assay_development_projects.id", ondelete="CASCADE"), index=True
    )
    question_key: Mapped[str] = mapped_column(String(200), index=True)
    plain_language_question: Mapped[str] = mapped_column(Text)
    formal_question: Mapped[str] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(40), default="OPEN", index=True)
    source: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_summary: Mapped[str | None] = mapped_column(Text)

    assay_project: Mapped[AssayDevelopmentProject] = relationship(back_populates="questions")


class Recommendation(UUIDPrimaryKeyMixin, Base):
    """Persisted output of a deterministic, inspectable guidance rule."""

    __tablename__ = "recommendations"
    __table_args__ = (
        Index(
            "ix_recommendations_active_rule",
            "assay_project_id",
            "rule_id",
            "status",
        ),
    )

    assay_project_id: Mapped[str] = mapped_column(
        ForeignKey("assay_development_projects.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[str] = mapped_column(String(36))
    rule_id: Mapped[str] = mapped_column(String(200), index=True)
    recommendation_type: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    why: Mapped[str] = mapped_column(Text)
    what_it_resolves: Mapped[str] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(String(40), index=True)
    priority: Mapped[int] = mapped_column(default=0)
    requirement_level: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(40), default="OPEN", index=True)
    required_inputs_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    expected_output: Mapped[str] = mapped_column(Text)
    proposed_action_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence_refs_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    assumptions_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    limitations_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    alternative_action_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assay_project: Mapped[AssayDevelopmentProject] = relationship(back_populates="recommendations")


class DecisionRecord(UUIDPrimaryKeyMixin, Base):
    """Immutable record of a material scientist choice and rationale."""

    __tablename__ = "decision_records"

    assay_project_id: Mapped[str] = mapped_column(
        ForeignKey("assay_development_projects.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    stage: Mapped[str] = mapped_column(String(40), index=True)
    decision_key: Mapped[str] = mapped_column(String(100), index=True)
    decision: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    selected_option: Mapped[str] = mapped_column(String(100))
    alternatives_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    evidence_refs_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    made_by: Mapped[str] = mapped_column(String(200), default="local-user")
    made_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    supersedes_decision_id: Mapped[str | None] = mapped_column(
        ForeignKey("decision_records.id", ondelete="SET NULL"), index=True
    )

    assay_project: Mapped[AssayDevelopmentProject] = relationship(back_populates="decisions")


class AssayAuditEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only audit event for the guided lifecycle."""

    __tablename__ = "assay_audit_events"

    assay_project_id: Mapped[str] = mapped_column(
        ForeignKey("assay_development_projects.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    actor: Mapped[str] = mapped_column(String(200))
    object_type: Mapped[str] = mapped_column(String(100))
    object_id: Mapped[str] = mapped_column(String(36), index=True)
    revision: Mapped[int | None]
    hashes_json: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    assay_project: Mapped[AssayDevelopmentProject] = relationship(back_populates="audit_events")


class GuidanceResult(UUIDPrimaryKeyMixin, Base):
    """Question-aware interpretation layered over an immutable analysis result."""

    __tablename__ = "guidance_results"

    assay_project_id: Mapped[str] = mapped_column(
        ForeignKey("assay_development_projects.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_questions.id", ondelete="RESTRICT"), index=True
    )
    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), unique=True, index=True
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    artifact_uri: Mapped[str] = mapped_column(String(2000), unique=True)
    artifact_sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    assay_project: Mapped[AssayDevelopmentProject] = relationship(back_populates="guidance_results")


class ExperimentPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Pre-lock experiment with one immutable execution revision once locked."""

    __tablename__ = "experiment_plans"

    assay_project_id: Mapped[str] = mapped_column(
        ForeignKey("assay_development_projects.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_questions.id", ondelete="RESTRICT"), index=True
    )
    prepared_dataset_id: Mapped[str] = mapped_column(
        ForeignKey("prepared_datasets.id", ondelete="RESTRICT"), index=True
    )
    parent_experiment_id: Mapped[str | None] = mapped_column(
        ForeignKey("experiment_plans.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), index=True)
    experiment_type: Mapped[str] = mapped_column(String(80), index=True)
    objective: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(50), default="DRAFT", index=True)
    experiment_spec_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    experiment_spec_uri: Mapped[str | None] = mapped_column(String(2000), unique=True)
    experiment_spec_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    assignments_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    assignments_uri: Mapped[str | None] = mapped_column(String(2000), unique=True)
    assignments_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    design_validation_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    development_bundle_uri: Mapped[str | None] = mapped_column(String(2000))
    current_revision: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[str] = mapped_column(String(200), default="local-user")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assay_project: Mapped[AssayDevelopmentProject] = relationship(back_populates="experiments")
    runs: Mapped[list[Run]] = relationship(back_populates="experiment")
    inputs: Mapped[list["ExperimentInput"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", passive_deletes=True
    )


class ExperimentInput(UUIDPrimaryKeyMixin, Base):
    """Immutable input reference for one Development Experiment."""

    __tablename__ = "experiment_inputs"

    experiment_id: Mapped[str] = mapped_column(
        ForeignKey("experiment_plans.id", ondelete="CASCADE"), index=True
    )
    input_type: Mapped[str] = mapped_column(String(80), index=True)
    prepared_dataset_id: Mapped[str | None] = mapped_column(
        ForeignKey("prepared_datasets.id", ondelete="RESTRICT"), index=True
    )
    analysis_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runs.id", ondelete="RESTRICT"), index=True
    )
    external_file_uri: Mapped[str | None] = mapped_column(String(2000))
    role: Mapped[str] = mapped_column(String(80))
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    experiment: Mapped[ExperimentPlan] = relationship(back_populates="inputs")


class AnalyticalStudy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Post-lock analytical validation study with an immutable execution revision."""

    __tablename__ = "analytical_studies"

    assay_project_id: Mapped[str] = mapped_column(
        ForeignKey("assay_development_projects.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_questions.id", ondelete="RESTRICT"), index=True
    )
    model_id: Mapped[str] = mapped_column(
        ForeignKey("model_records.id", ondelete="RESTRICT"), index=True
    )
    prepared_dataset_id: Mapped[str] = mapped_column(
        ForeignKey("prepared_datasets.id", ondelete="RESTRICT"), index=True
    )
    parent_study_id: Mapped[str | None] = mapped_column(
        ForeignKey("analytical_studies.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), index=True)
    study_type: Mapped[str] = mapped_column(String(80), index=True)
    objective: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="DRAFT", index=True)
    study_spec_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    assignments_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    criteria_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    design_validation_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    study_spec_uri: Mapped[str | None] = mapped_column(String(2000), unique=True)
    study_spec_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    assignments_uri: Mapped[str | None] = mapped_column(String(2000), unique=True)
    assignments_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    validation_bundle_uri: Mapped[str | None] = mapped_column(String(2000))
    current_revision: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[str] = mapped_column(String(200), default="local-user")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assay_project: Mapped[AssayDevelopmentProject] = relationship(back_populates="studies")
    runs: Mapped[list[Run]] = relationship(back_populates="study")
    inputs: Mapped[list["StudyInput"]] = relationship(
        back_populates="study", cascade="all, delete-orphan", passive_deletes=True
    )
    criteria: Mapped[list["AcceptanceCriterion"]] = relationship(
        back_populates="study", cascade="all, delete-orphan", passive_deletes=True
    )
    validation_results: Mapped[list["ValidationResult"]] = relationship(
        back_populates="study", cascade="all, delete-orphan", passive_deletes=True
    )


class StudyInput(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "study_inputs"

    study_id: Mapped[str] = mapped_column(
        ForeignKey("analytical_studies.id", ondelete="CASCADE"), index=True
    )
    input_type: Mapped[str] = mapped_column(String(80), index=True)
    object_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(80))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    study: Mapped[AnalyticalStudy] = relationship(back_populates="inputs")


class AcceptanceCriterion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "acceptance_criteria"

    study_id: Mapped[str] = mapped_column(
        ForeignKey("analytical_studies.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(100), index=True)
    metric: Mapped[str] = mapped_column(String(100))
    endpoint: Mapped[str] = mapped_column(String(100))
    operator: Mapped[str] = mapped_column(String(40))
    threshold_json: Mapped[Any] = mapped_column(JSON)
    rationale: Mapped[str] = mapped_column(Text)
    result_status: Mapped[str] = mapped_column(String(40), default="NOT_EVALUATED")
    observed_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    study: Mapped[AnalyticalStudy] = relationship(back_populates="criteria")


class ValidationResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "validation_results"

    study_id: Mapped[str] = mapped_column(
        ForeignKey("analytical_studies.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), unique=True, index=True
    )
    overall_status: Mapped[str] = mapped_column(String(40), index=True)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    bundle_uri: Mapped[str] = mapped_column(String(2000), unique=True)
    bundle_sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    study: Mapped[AnalyticalStudy] = relationship(back_populates="validation_results")
