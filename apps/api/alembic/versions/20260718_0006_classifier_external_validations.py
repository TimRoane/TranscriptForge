"""Persist imported one-shot classifier external validation studies.

Revision ID: 20260718_0006
Revises: 20260717_0005
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_0006"
down_revision: str | None = "20260717_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "classifier_external_validations",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("development_accession", sa.String(length=40), nullable=False),
        sa.Column("external_accession", sa.String(length=40), nullable=False),
        sa.Column("protocol_id", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("development_summary_json", sa.JSON(), nullable=False),
        sa.Column("prediction_summary_json", sa.JSON(), nullable=True),
        sa.Column("protocol_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("artifacts_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name=op.f("fk_classifier_external_validations_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_classifier_external_validations")),
        sa.UniqueConstraint("protocol_id", name=op.f("uq_classifier_external_validations_protocol_id")),
    )
    op.create_index(
        op.f("ix_classifier_external_validations_development_accession"),
        "classifier_external_validations", ["development_accession"], unique=False,
    )
    op.create_index(
        op.f("ix_classifier_external_validations_external_accession"),
        "classifier_external_validations", ["external_accession"], unique=False,
    )
    op.create_index(
        op.f("ix_classifier_external_validations_project_id"),
        "classifier_external_validations", ["project_id"], unique=False,
    )
    op.create_index(
        op.f("ix_classifier_external_validations_protocol_id"),
        "classifier_external_validations", ["protocol_id"], unique=True,
    )
    op.create_index(
        op.f("ix_classifier_external_validations_status"),
        "classifier_external_validations", ["status"], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_classifier_external_validations_status"), table_name="classifier_external_validations")
    op.drop_index(op.f("ix_classifier_external_validations_protocol_id"), table_name="classifier_external_validations")
    op.drop_index(op.f("ix_classifier_external_validations_project_id"), table_name="classifier_external_validations")
    op.drop_index(op.f("ix_classifier_external_validations_external_accession"), table_name="classifier_external_validations")
    op.drop_index(op.f("ix_classifier_external_validations_development_accession"), table_name="classifier_external_validations")
    op.drop_table("classifier_external_validations")
