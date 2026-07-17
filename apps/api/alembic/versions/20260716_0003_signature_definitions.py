"""Add immutable uploaded signature definitions.

Revision ID: 20260716_0003
Revises: 20260716_0002
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260716_0003"
down_revision: str | None = "20260716_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
ID = sa.String(length=36)


def upgrade() -> None:
    op.create_table(
        "signature_definitions",
        sa.Column("project_id", ID, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("definition_format", sa.String(40), nullable=False),
        sa.Column("identifier_type", sa.String(40), nullable=False),
        sa.Column("original_name", sa.String(500), nullable=False),
        sa.Column("source_uri", sa.String(2000), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("manifest_uri", sa.String(2000), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("set_count", sa.Integer(), nullable=False),
        sa.Column("requested_identifier_count", sa.Integer(), nullable=False),
        sa.Column("unique_identifier_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_identifier_count", sa.Integer(), nullable=False),
        sa.Column("weighted", sa.Boolean(), nullable=False),
        sa.Column("definition_json", sa.JSON(), nullable=False),
        sa.Column("id", ID, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_signature_definitions"),
        sa.UniqueConstraint("source_uri"),
        sa.UniqueConstraint("manifest_uri"),
    )
    op.create_index("ix_signature_definitions_project_id", "signature_definitions", ["project_id"])
    op.create_index("ix_signature_definitions_name", "signature_definitions", ["name"])
    op.create_index(
        "ix_signature_definitions_source_sha256", "signature_definitions", ["source_sha256"]
    )


def downgrade() -> None:
    op.drop_table("signature_definitions")
