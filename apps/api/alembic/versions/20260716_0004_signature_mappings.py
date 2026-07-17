"""Add immutable signature-to-bundle mappings.

Revision ID: 20260716_0004
Revises: 20260716_0003
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260716_0004"
down_revision: str | None = "20260716_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
ID = sa.String(length=36)


def upgrade() -> None:
    op.create_table(
        "signature_mappings",
        sa.Column("signature_definition_id", ID, nullable=False),
        sa.Column("prepared_dataset_id", ID, nullable=False),
        sa.Column("report_uri", sa.String(2000), nullable=False, unique=True),
        sa.Column("report_sha256", sa.String(64), nullable=False),
        sa.Column("missing_uri", sa.String(2000), nullable=False, unique=True),
        sa.Column("missing_sha256", sa.String(64), nullable=False),
        sa.Column("ambiguous_uri", sa.String(2000), nullable=False, unique=True),
        sa.Column("ambiguous_sha256", sa.String(64), nullable=False),
        sa.Column("requested_identifier_count", sa.Integer(), nullable=False),
        sa.Column("unique_identifier_count", sa.Integer(), nullable=False),
        sa.Column("mapped_identifier_count", sa.Integer(), nullable=False),
        sa.Column("missing_identifier_count", sa.Integer(), nullable=False),
        sa.Column("ambiguous_identifier_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_identifier_count", sa.Integer(), nullable=False),
        sa.Column("mapping_coverage", sa.Float(), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("id", ID, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["signature_definition_id"], ["signature_definitions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["prepared_dataset_id"], ["prepared_datasets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_signature_mappings"),
    )
    op.create_index(
        "ix_signature_mappings_signature_definition_id",
        "signature_mappings",
        ["signature_definition_id"],
    )
    op.create_index(
        "ix_signature_mappings_prepared_dataset_id", "signature_mappings", ["prepared_dataset_id"]
    )
    op.create_index(
        "uq_signature_mapping_definition_prepared",
        "signature_mappings",
        ["signature_definition_id", "prepared_dataset_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("signature_mappings")
