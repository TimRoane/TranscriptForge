"""Make project-owned execution metadata deletable as one graph.

Revision ID: 20260717_0005
Revises: 20260716_0004
Create Date: 2026-07-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260717_0005"
down_revision: str | None = "20260716_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def replace_foreign_key(
    table: str,
    name: str,
    columns: list[str],
    referenced_table: str,
    referenced_columns: list[str],
    *,
    ondelete: str | None,
) -> None:
    op.drop_constraint(name, table, type_="foreignkey")
    op.create_foreign_key(
        name,
        table,
        referenced_table,
        columns,
        referenced_columns,
        ondelete=ondelete,
    )


def upgrade() -> None:
    replace_foreign_key(
        "prepared_datasets",
        "fk_prepared_datasets_preparation_run_id_runs",
        ["preparation_run_id"],
        "runs",
        ["id"],
        ondelete="SET NULL",
    )
    replace_foreign_key(
        "analyses",
        "fk_analyses_prepared_dataset_id_prepared_datasets",
        ["prepared_dataset_id"],
        "prepared_datasets",
        ["id"],
        ondelete="CASCADE",
    )
    replace_foreign_key(
        "runs",
        "fk_runs_dataset_id_datasets",
        ["dataset_id"],
        "datasets",
        ["id"],
        ondelete="CASCADE",
    )
    replace_foreign_key(
        "runs",
        "fk_runs_prepared_dataset_id_prepared_datasets",
        ["prepared_dataset_id"],
        "prepared_datasets",
        ["id"],
        ondelete="CASCADE",
    )
    replace_foreign_key(
        "runs",
        "fk_runs_analysis_id_analyses",
        ["analysis_id"],
        "analyses",
        ["id"],
        ondelete="CASCADE",
    )
    replace_foreign_key(
        "model_records",
        "fk_model_records_analysis_id_analyses",
        ["analysis_id"],
        "analyses",
        ["id"],
        ondelete="CASCADE",
    )
    replace_foreign_key(
        "model_records",
        "fk_model_records_run_id_runs",
        ["run_id"],
        "runs",
        ["id"],
        ondelete="CASCADE",
    )
    replace_foreign_key(
        "gene_signatures",
        "fk_gene_signatures_prepared_dataset_id_prepared_datasets",
        ["prepared_dataset_id"],
        "prepared_datasets",
        ["id"],
        ondelete="CASCADE",
    )
    replace_foreign_key(
        "gene_signatures",
        "fk_gene_signatures_source_analysis_id_analyses",
        ["source_analysis_id"],
        "analyses",
        ["id"],
        ondelete="CASCADE",
    )
    replace_foreign_key(
        "gene_signatures",
        "fk_gene_signatures_source_run_id_runs",
        ["source_run_id"],
        "runs",
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    replace_foreign_key(
        "gene_signatures",
        "fk_gene_signatures_source_run_id_runs",
        ["source_run_id"],
        "runs",
        ["id"],
        ondelete="RESTRICT",
    )
    replace_foreign_key(
        "gene_signatures",
        "fk_gene_signatures_source_analysis_id_analyses",
        ["source_analysis_id"],
        "analyses",
        ["id"],
        ondelete="RESTRICT",
    )
    replace_foreign_key(
        "gene_signatures",
        "fk_gene_signatures_prepared_dataset_id_prepared_datasets",
        ["prepared_dataset_id"],
        "prepared_datasets",
        ["id"],
        ondelete="RESTRICT",
    )
    replace_foreign_key(
        "model_records",
        "fk_model_records_run_id_runs",
        ["run_id"],
        "runs",
        ["id"],
        ondelete=None,
    )
    replace_foreign_key(
        "model_records",
        "fk_model_records_analysis_id_analyses",
        ["analysis_id"],
        "analyses",
        ["id"],
        ondelete=None,
    )
    replace_foreign_key(
        "runs",
        "fk_runs_analysis_id_analyses",
        ["analysis_id"],
        "analyses",
        ["id"],
        ondelete=None,
    )
    replace_foreign_key(
        "runs",
        "fk_runs_prepared_dataset_id_prepared_datasets",
        ["prepared_dataset_id"],
        "prepared_datasets",
        ["id"],
        ondelete=None,
    )
    replace_foreign_key(
        "runs",
        "fk_runs_dataset_id_datasets",
        ["dataset_id"],
        "datasets",
        ["id"],
        ondelete=None,
    )
    replace_foreign_key(
        "analyses",
        "fk_analyses_prepared_dataset_id_prepared_datasets",
        ["prepared_dataset_id"],
        "prepared_datasets",
        ["id"],
        ondelete="RESTRICT",
    )
    replace_foreign_key(
        "prepared_datasets",
        "fk_prepared_datasets_preparation_run_id_runs",
        ["preparation_run_id"],
        "runs",
        ["id"],
        ondelete=None,
    )
