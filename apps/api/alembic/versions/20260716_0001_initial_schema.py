"""Create the initial TranscriptForge persistence schema.

Revision ID: 20260716_0001
Revises: None
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260716_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID = sa.String(length=36)
URI = sa.String(length=2000)


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.String(200), nullable=False, server_default="local-user"),
        sa.Column("id", ID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
    )
    op.create_index("ix_projects_name", "projects", ["name"])
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])

    op.create_table(
        "datasets",
        sa.Column("project_id", ID, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("modality", sa.String(40), nullable=False),
        sa.Column("source_kind", sa.String(40), nullable=False),
        sa.Column("organism", sa.String(100), nullable=False, server_default="Homo sapiens"),
        sa.Column("genome_build", sa.String(100), nullable=True),
        sa.Column("annotation_release", sa.String(100), nullable=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="draft"),
        sa.Column("id", ID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_datasets_project_id_projects", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_datasets"),
    )
    op.create_index("ix_datasets_project_id", "datasets", ["project_id"])
    op.create_index("ix_datasets_name", "datasets", ["name"])

    op.create_table(
        "dataset_files",
        sa.Column("dataset_id", ID, nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("original_name", sa.String(500), nullable=False),
        sa.Column("storage_uri", URI, nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", ID, nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name="fk_dataset_files_dataset_id_datasets", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dataset_files"),
        sa.UniqueConstraint("storage_uri", name="uq_dataset_files_storage_uri"),
    )
    op.create_index("ix_dataset_files_dataset_id", "dataset_files", ["dataset_id"])
    op.create_index("ix_dataset_files_role", "dataset_files", ["role"])
    op.create_index("ix_dataset_files_sha256", "dataset_files", ["sha256"])

    op.create_table(
        "prepared_datasets",
        sa.Column("dataset_id", ID, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("preparation_run_id", ID, nullable=True),
        sa.Column("bundle_uri", URI, nullable=False),
        sa.Column("bundle_manifest_uri", URI, nullable=False),
        sa.Column("value_types_available", sa.JSON(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("feature_count", sa.Integer(), nullable=False),
        sa.Column("qc_status", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", ID, nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name="fk_prepared_datasets_dataset_id_datasets", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_prepared_datasets"),
        sa.UniqueConstraint("preparation_run_id", name="uq_prepared_datasets_preparation_run_id"),
        sa.UniqueConstraint("bundle_uri", name="uq_prepared_datasets_bundle_uri"),
        sa.UniqueConstraint("bundle_manifest_uri", name="uq_prepared_datasets_bundle_manifest_uri"),
    )
    op.create_index("ix_prepared_datasets_dataset_id", "prepared_datasets", ["dataset_id"])
    op.create_index(
        "uq_prepared_dataset_version", "prepared_datasets", ["dataset_id", "version"], unique=True
    )

    op.create_table(
        "analyses",
        sa.Column("project_id", ID, nullable=False),
        sa.Column("prepared_dataset_id", ID, nullable=False),
        sa.Column("analysis_type", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("configuration_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", ID, nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_analyses_project_id_projects", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["prepared_dataset_id"],
            ["prepared_datasets.id"],
            name="fk_analyses_prepared_dataset_id_prepared_datasets",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_analyses"),
    )
    op.create_index("ix_analyses_project_id", "analyses", ["project_id"])
    op.create_index("ix_analyses_prepared_dataset_id", "analyses", ["prepared_dataset_id"])
    op.create_index("ix_analyses_analysis_type", "analyses", ["analysis_type"])

    op.create_table(
        "runs",
        sa.Column("run_type", sa.String(40), nullable=False),
        sa.Column("dataset_id", ID, nullable=True),
        sa.Column("prepared_dataset_id", ID, nullable=True),
        sa.Column("analysis_id", ID, nullable=True),
        sa.Column("state", sa.String(30), nullable=False, server_default="CREATED"),
        sa.Column("profile", sa.String(50), nullable=False, server_default="docker"),
        sa.Column("params_uri", URI, nullable=False),
        sa.Column("output_uri", URI, nullable=False),
        sa.Column("work_uri", URI, nullable=False),
        sa.Column("nextflow_session_id", sa.String(200), nullable=True),
        sa.Column("nextflow_run_name", sa.String(200), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", ID, nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], name="fk_runs_dataset_id_datasets"),
        sa.ForeignKeyConstraint(
            ["prepared_dataset_id"], ["prepared_datasets.id"], name="fk_runs_prepared_dataset_id_prepared_datasets"
        ),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], name="fk_runs_analysis_id_analyses"),
        sa.PrimaryKeyConstraint("id", name="pk_runs"),
    )
    op.create_index("ix_runs_run_type", "runs", ["run_type"])
    op.create_index("ix_runs_dataset_id", "runs", ["dataset_id"])
    op.create_index("ix_runs_prepared_dataset_id", "runs", ["prepared_dataset_id"])
    op.create_index("ix_runs_analysis_id", "runs", ["analysis_id"])
    op.create_index("ix_runs_state", "runs", ["state"])
    op.create_foreign_key(
        "fk_prepared_datasets_preparation_run_id_runs",
        "prepared_datasets",
        "runs",
        ["preparation_run_id"],
        ["id"],
    )

    op.create_table(
        "artifacts",
        sa.Column("run_id", ID, nullable=False),
        sa.Column("artifact_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("relative_path", URI, nullable=False),
        sa.Column("storage_uri", URI, nullable=False),
        sa.Column("mime_type", sa.String(200), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("id", ID, nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name="fk_artifacts_run_id_runs", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_artifacts"),
        sa.UniqueConstraint("storage_uri", name="uq_artifacts_storage_uri"),
    )
    op.create_index("ix_artifacts_run_id", "artifacts", ["run_id"])
    op.create_index("ix_artifacts_artifact_type", "artifacts", ["artifact_type"])

    op.create_table(
        "model_records",
        sa.Column("analysis_id", ID, nullable=False),
        sa.Column("run_id", ID, nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("algorithm", sa.String(100), nullable=False),
        sa.Column("outcome_column", sa.String(200), nullable=False),
        sa.Column("model_uri", URI, nullable=False),
        sa.Column("model_card_uri", URI, nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("feature_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", ID, nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"], ["analyses.id"], name="fk_model_records_analysis_id_analyses"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], name="fk_model_records_run_id_runs"),
        sa.PrimaryKeyConstraint("id", name="pk_model_records"),
        sa.UniqueConstraint("model_uri", name="uq_model_records_model_uri"),
        sa.UniqueConstraint("model_card_uri", name="uq_model_records_model_card_uri"),
    )
    op.create_index("ix_model_records_analysis_id", "model_records", ["analysis_id"])
    op.create_index("ix_model_records_run_id", "model_records", ["run_id"])


def downgrade() -> None:
    op.drop_table("model_records")
    op.drop_table("artifacts")
    op.drop_constraint(
        "fk_prepared_datasets_preparation_run_id_runs", "prepared_datasets", type_="foreignkey"
    )
    op.drop_table("runs")
    op.drop_table("analyses")
    op.drop_table("prepared_datasets")
    op.drop_table("dataset_files")
    op.drop_table("datasets")
    op.drop_table("projects")
