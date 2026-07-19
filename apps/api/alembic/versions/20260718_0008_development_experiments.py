"""Add pre-lock Development Experiments and their immutable inputs.

Revision ID: 20260718_0008
Revises: 20260718_0007
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_0008"
down_revision: str | None = "20260718_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "experiment_plans",
        sa.Column("assay_project_id", sa.String(), nullable=False),
        sa.Column("question_id", sa.String(), nullable=False),
        sa.Column("prepared_dataset_id", sa.String(), nullable=False),
        sa.Column("parent_experiment_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("experiment_type", sa.String(length=80), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("experiment_spec_json", sa.JSON(), nullable=False),
        sa.Column("experiment_spec_uri", sa.String(length=2000), nullable=True),
        sa.Column("experiment_spec_sha256", sa.String(length=64), nullable=True),
        sa.Column("assignments_json", sa.JSON(), nullable=False),
        sa.Column("assignments_uri", sa.String(length=2000), nullable=True),
        sa.Column("assignments_sha256", sa.String(length=64), nullable=True),
        sa.Column("design_validation_json", sa.JSON(), nullable=True),
        sa.Column("development_bundle_uri", sa.String(length=2000), nullable=True),
        sa.Column("current_revision", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["assay_project_id"], ["assay_development_projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["question_id"], ["scientific_questions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["prepared_dataset_id"], ["prepared_datasets.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["parent_experiment_id"], ["experiment_plans.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_spec_uri"),
        sa.UniqueConstraint("assignments_uri"),
    )
    for column in (
        "assay_project_id",
        "question_id",
        "prepared_dataset_id",
        "parent_experiment_id",
        "name",
        "experiment_type",
        "status",
        "experiment_spec_sha256",
        "assignments_sha256",
    ):
        op.create_index(op.f(f"ix_experiment_plans_{column}"), "experiment_plans", [column])

    op.add_column("runs", sa.Column("experiment_id", sa.String(), nullable=True))
    op.create_foreign_key(
        op.f("fk_runs_experiment_id_experiment_plans"),
        "runs",
        "experiment_plans",
        ["experiment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_runs_experiment_id"), "runs", ["experiment_id"])

    op.create_table(
        "experiment_inputs",
        sa.Column("experiment_id", sa.String(), nullable=False),
        sa.Column("input_type", sa.String(length=80), nullable=False),
        sa.Column("prepared_dataset_id", sa.String(), nullable=True),
        sa.Column("analysis_run_id", sa.String(), nullable=True),
        sa.Column("external_file_uri", sa.String(length=2000), nullable=True),
        sa.Column("role", sa.String(length=80), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiment_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["prepared_dataset_id"], ["prepared_datasets.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "experiment_id",
        "input_type",
        "prepared_dataset_id",
        "analysis_run_id",
        "sha256",
    ):
        op.create_index(op.f(f"ix_experiment_inputs_{column}"), "experiment_inputs", [column])


def downgrade() -> None:
    op.drop_table("experiment_inputs")
    op.drop_index(op.f("ix_runs_experiment_id"), table_name="runs")
    op.drop_constraint(op.f("fk_runs_experiment_id_experiment_plans"), "runs", type_="foreignkey")
    op.drop_column("runs", "experiment_id")
    op.drop_table("experiment_plans")
