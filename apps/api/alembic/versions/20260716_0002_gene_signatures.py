"""Add provenance-frozen candidate gene signature drafts.

Revision ID: 20260716_0002
Revises: 20260716_0001
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260716_0002"
down_revision: str | None = "20260716_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID = sa.String(length=36)


def upgrade() -> None:
    op.create_table(
        "gene_signatures",
        sa.Column("project_id", ID, nullable=False),
        sa.Column("prepared_dataset_id", ID, nullable=False),
        sa.Column("source_analysis_id", ID, nullable=False),
        sa.Column("source_run_id", ID, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="draft"),
        sa.Column("feature_ids", sa.JSON(), nullable=False),
        sa.Column("feature_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("selection_json", sa.JSON(), nullable=False),
        sa.Column("id", ID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_gene_signatures_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["prepared_dataset_id"], ["prepared_datasets.id"],
            name="fk_gene_signatures_prepared_dataset_id_prepared_datasets", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_analysis_id"], ["analyses.id"],
            name="fk_gene_signatures_source_analysis_id_analyses", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"], ["runs.id"],
            name="fk_gene_signatures_source_run_id_runs", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_gene_signatures"),
    )
    op.create_index("ix_gene_signatures_project_id", "gene_signatures", ["project_id"])
    op.create_index(
        "ix_gene_signatures_prepared_dataset_id", "gene_signatures", ["prepared_dataset_id"]
    )
    op.create_index(
        "ix_gene_signatures_source_analysis_id", "gene_signatures", ["source_analysis_id"]
    )
    op.create_index("ix_gene_signatures_source_run_id", "gene_signatures", ["source_run_id"])
    op.create_index("ix_gene_signatures_name", "gene_signatures", ["name"])


def downgrade() -> None:
    op.drop_table("gene_signatures")
