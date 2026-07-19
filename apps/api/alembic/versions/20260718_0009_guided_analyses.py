"""Link guided analyses and persist question-aware GuidanceResults.

Revision ID: 20260718_0009
Revises: 20260718_0008
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_0009"
down_revision: str | None = "20260718_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("assay_project_id", sa.String(), nullable=True))
    op.add_column("analyses", sa.Column("scientific_question_id", sa.String(), nullable=True))
    op.create_foreign_key(
        op.f("fk_analyses_assay_project_id_assay_development_projects"),
        "analyses",
        "assay_development_projects",
        ["assay_project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        op.f("fk_analyses_scientific_question_id_scientific_questions"),
        "analyses",
        "scientific_questions",
        ["scientific_question_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_analyses_assay_project_id"), "analyses", ["assay_project_id"])
    op.create_index(
        op.f("ix_analyses_scientific_question_id"), "analyses", ["scientific_question_id"]
    )
    op.create_table(
        "guidance_results",
        sa.Column("assay_project_id", sa.String(), nullable=False),
        sa.Column("question_id", sa.String(), nullable=False),
        sa.Column("analysis_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("artifact_uri", sa.String(length=2000), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assay_project_id"], ["assay_development_projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["question_id"], ["scientific_questions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
        sa.UniqueConstraint("artifact_uri"),
    )
    for column in ("assay_project_id", "question_id", "analysis_id", "run_id", "artifact_sha256"):
        op.create_index(op.f(f"ix_guidance_results_{column}"), "guidance_results", [column])


def downgrade() -> None:
    op.drop_table("guidance_results")
    op.drop_index(op.f("ix_analyses_scientific_question_id"), table_name="analyses")
    op.drop_index(op.f("ix_analyses_assay_project_id"), table_name="analyses")
    op.drop_constraint(
        op.f("fk_analyses_scientific_question_id_scientific_questions"),
        "analyses",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_analyses_assay_project_id_assay_development_projects"),
        "analyses",
        type_="foreignkey",
    )
    op.drop_column("analyses", "scientific_question_id")
    op.drop_column("analyses", "assay_project_id")
