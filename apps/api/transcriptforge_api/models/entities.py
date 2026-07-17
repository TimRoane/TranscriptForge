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
    __table_args__ = (
        Index("uq_prepared_dataset_version", "dataset_id", "version", unique=True),
    )

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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    run: Mapped[Run] = relationship(back_populates="model_records")


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
