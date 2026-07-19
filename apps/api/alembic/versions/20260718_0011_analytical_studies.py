"""Add post-lock analytical studies, criteria, inputs, and results.

Revision ID: 20260718_0011
Revises: 20260718_0010
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_0011"
down_revision: str | None = "20260718_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analytical_studies",
        sa.Column("assay_project_id", sa.String(), nullable=False),
        sa.Column("question_id", sa.String(), nullable=False),
        sa.Column("model_id", sa.String(), nullable=False),
        sa.Column("prepared_dataset_id", sa.String(), nullable=False),
        sa.Column("parent_study_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("study_type", sa.String(80), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("study_spec_json", sa.JSON(), nullable=False),
        sa.Column("assignments_json", sa.JSON(), nullable=False),
        sa.Column("criteria_json", sa.JSON(), nullable=False),
        sa.Column("design_validation_json", sa.JSON(), nullable=True),
        sa.Column("study_spec_uri", sa.String(2000), nullable=True, unique=True),
        sa.Column("study_spec_sha256", sa.String(64), nullable=True),
        sa.Column("assignments_uri", sa.String(2000), nullable=True, unique=True),
        sa.Column("assignments_sha256", sa.String(64), nullable=True),
        sa.Column("validation_bundle_uri", sa.String(2000), nullable=True),
        sa.Column("current_revision", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(200), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(), primary_key=True),
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
        sa.ForeignKeyConstraint(["model_id"], ["model_records.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["prepared_dataset_id"], ["prepared_datasets.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["parent_study_id"], ["analytical_studies.id"], ondelete="SET NULL"
        ),
    )
    for column in (
        "assay_project_id",
        "question_id",
        "model_id",
        "prepared_dataset_id",
        "parent_study_id",
        "name",
        "study_type",
        "status",
        "study_spec_sha256",
        "assignments_sha256",
    ):
        op.create_index(op.f(f"ix_analytical_studies_{column}"), "analytical_studies", [column])
    op.add_column("runs", sa.Column("study_id", sa.String(), nullable=True))
    op.create_foreign_key(
        op.f("fk_runs_study_id_analytical_studies"),
        "runs",
        "analytical_studies",
        ["study_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_runs_study_id"), "runs", ["study_id"])
    op.create_table(
        "study_inputs",
        sa.Column("study_id", sa.String(), nullable=False),
        sa.Column("input_type", sa.String(80), nullable=False),
        sa.Column("object_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(80), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", sa.String(), primary_key=True),
        sa.ForeignKeyConstraint(["study_id"], ["analytical_studies.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "acceptance_criteria",
        sa.Column("study_id", sa.String(), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("metric", sa.String(100), nullable=False),
        sa.Column("endpoint", sa.String(100), nullable=False),
        sa.Column("operator", sa.String(40), nullable=False),
        sa.Column("threshold_json", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("result_status", sa.String(40), nullable=False),
        sa.Column("observed_json", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(), primary_key=True),
        sa.ForeignKeyConstraint(["study_id"], ["analytical_studies.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "validation_results",
        sa.Column("study_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False, unique=True),
        sa.Column("overall_status", sa.String(40), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("bundle_uri", sa.String(2000), nullable=False, unique=True),
        sa.Column("bundle_sha256", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", sa.String(), primary_key=True),
        sa.ForeignKeyConstraint(["study_id"], ["analytical_studies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
    )
    for table, columns in (
        ("study_inputs", ("study_id", "input_type", "object_id", "sha256")),
        ("acceptance_criteria", ("study_id", "key")),
        ("validation_results", ("study_id", "run_id", "overall_status", "bundle_sha256")),
    ):
        for column in columns:
            op.create_index(op.f(f"ix_{table}_{column}"), table, [column])


def downgrade() -> None:
    op.drop_table("validation_results")
    op.drop_table("acceptance_criteria")
    op.drop_table("study_inputs")
    op.drop_index(op.f("ix_runs_study_id"), table_name="runs")
    op.drop_constraint(op.f("fk_runs_study_id_analytical_studies"), "runs", type_="foreignkey")
    op.drop_column("runs", "study_id")
    op.drop_table("analytical_studies")
