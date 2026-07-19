"""Add guided assay-development projects, questions, guidance, and decisions.

Revision ID: 20260718_0007
Revises: 20260718_0006
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_0007"
down_revision: str | None = "20260718_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assay_development_projects",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("proposed_purpose", sa.Text(), nullable=True),
        sa.Column("specimen_type", sa.String(length=200), nullable=True),
        sa.Column("biological_context", sa.Text(), nullable=True),
        sa.Column("proposed_output", sa.String(length=500), nullable=True),
        sa.Column("current_stage", sa.String(length=40), nullable=False),
        sa.Column("readiness_status", sa.String(length=50), nullable=False),
        sa.Column("active_question_id", sa.String(length=36), nullable=True),
        sa.Column("assay_version", sa.String(length=200), nullable=True),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )
    for column in ("project_id", "name", "current_stage", "readiness_status", "active_question_id"):
        op.create_index(
            op.f(f"ix_assay_development_projects_{column}"), "assay_development_projects", [column]
        )

    op.create_table(
        "scientific_questions",
        sa.Column("assay_project_id", sa.String(), nullable=False),
        sa.Column("question_key", sa.String(length=200), nullable=False),
        sa.Column("plain_language_question", sa.Text(), nullable=False),
        sa.Column("formal_question", sa.Text(), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_summary", sa.Text(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assay_project_id"], ["assay_development_projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("assay_project_id", "question_key", "stage", "status"):
        op.create_index(op.f(f"ix_scientific_questions_{column}"), "scientific_questions", [column])

    op.create_table(
        "recommendations",
        sa.Column("assay_project_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=200), nullable=False),
        sa.Column("recommendation_type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("why", sa.Text(), nullable=False),
        sa.Column("what_it_resolves", sa.Text(), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("requirement_level", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("required_inputs_json", sa.JSON(), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=False),
        sa.Column("proposed_action_json", sa.JSON(), nullable=False),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
        sa.Column("assumptions_json", sa.JSON(), nullable=False),
        sa.Column("limitations_json", sa.JSON(), nullable=False),
        sa.Column("alternative_action_ids_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assay_project_id"], ["assay_development_projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("assay_project_id", "rule_id", "stage", "requirement_level", "status"):
        op.create_index(op.f(f"ix_recommendations_{column}"), "recommendations", [column])
    op.create_index(
        "ix_recommendations_active_rule",
        "recommendations",
        ["assay_project_id", "rule_id", "status"],
    )

    op.create_table(
        "decision_records",
        sa.Column("assay_project_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("decision_key", sa.String(length=100), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("selected_option", sa.String(length=100), nullable=False),
        sa.Column("alternatives_json", sa.JSON(), nullable=False),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
        sa.Column("made_by", sa.String(length=200), nullable=False),
        sa.Column(
            "made_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("supersedes_decision_id", sa.String(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assay_project_id"], ["assay_development_projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_decision_id"], ["decision_records.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "assay_project_id",
        "source_id",
        "stage",
        "decision_key",
        "supersedes_decision_id",
    ):
        op.create_index(op.f(f"ix_decision_records_{column}"), "decision_records", [column])

    op.create_table(
        "assay_audit_events",
        sa.Column("assay_project_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("object_type", sa.String(length=100), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=True),
        sa.Column("hashes_json", sa.JSON(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assay_project_id"], ["assay_development_projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("assay_project_id", "event_type", "object_id"):
        op.create_index(op.f(f"ix_assay_audit_events_{column}"), "assay_audit_events", [column])


def downgrade() -> None:
    op.drop_table("assay_audit_events")
    op.drop_table("decision_records")
    op.drop_table("recommendations")
    op.drop_table("scientific_questions")
    op.drop_table("assay_development_projects")
