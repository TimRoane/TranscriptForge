"""Add immutable classifier model review and lock lifecycle.

Revision ID: 20260718_0010
Revises: 20260718_0009
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260718_0010"
down_revision: str | None = "20260718_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = [
        sa.Column("status", sa.String(length=30), nullable=False, server_default="CANDIDATE"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(length=200), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=200), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parent_model_id", sa.String(), nullable=True),
        sa.Column("model_manifest_uri", sa.String(length=2000), nullable=True),
        sa.Column("model_manifest_sha256", sa.String(length=64), nullable=True),
        sa.Column("model_package_uri", sa.String(length=2000), nullable=True),
        sa.Column("model_package_sha256", sa.String(length=64), nullable=True),
        sa.Column("feature_schema_sha256", sa.String(length=64), nullable=True),
        sa.Column("preprocessing_sha256", sa.String(length=64), nullable=True),
        sa.Column("model_object_sha256", sa.String(length=64), nullable=True),
        sa.Column("threshold_sha256", sa.String(length=64), nullable=True),
        sa.Column("training_dataset_refs_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("validation_dataset_refs_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("container_digest", sa.String(length=80), nullable=True),
        sa.Column(
            "inference_test_status", sa.String(length=30), nullable=False, server_default="NOT_RUN"
        ),
    ]
    for column in columns:
        op.add_column("model_records", column)
    op.create_foreign_key(
        op.f("fk_model_records_parent_model_id_model_records"),
        "model_records",
        "model_records",
        ["parent_model_id"],
        ["id"],
        ondelete="SET NULL",
    )
    for column in (
        "status",
        "parent_model_id",
        "model_manifest_sha256",
        "model_package_sha256",
        "feature_schema_sha256",
        "preprocessing_sha256",
        "model_object_sha256",
        "threshold_sha256",
    ):
        op.create_index(op.f(f"ix_model_records_{column}"), "model_records", [column])
    op.create_unique_constraint(
        op.f("uq_model_records_model_manifest_uri"), "model_records", ["model_manifest_uri"]
    )
    op.create_unique_constraint(
        op.f("uq_model_records_model_package_uri"), "model_records", ["model_package_uri"]
    )


def downgrade() -> None:
    op.drop_constraint(op.f("uq_model_records_model_package_uri"), "model_records", type_="unique")
    op.drop_constraint(op.f("uq_model_records_model_manifest_uri"), "model_records", type_="unique")
    op.drop_constraint(
        op.f("fk_model_records_parent_model_id_model_records"), "model_records", type_="foreignkey"
    )
    for column in reversed(
        (
            "status",
            "parent_model_id",
            "model_manifest_sha256",
            "model_package_sha256",
            "feature_schema_sha256",
            "preprocessing_sha256",
            "model_object_sha256",
            "threshold_sha256",
        )
    ):
        op.drop_index(op.f(f"ix_model_records_{column}"), table_name="model_records")
    for column in reversed(
        (
            "status",
            "reviewed_at",
            "reviewed_by",
            "locked_at",
            "locked_by",
            "retired_at",
            "parent_model_id",
            "model_manifest_uri",
            "model_manifest_sha256",
            "model_package_uri",
            "model_package_sha256",
            "feature_schema_sha256",
            "preprocessing_sha256",
            "model_object_sha256",
            "threshold_sha256",
            "training_dataset_refs_json",
            "validation_dataset_refs_json",
            "container_digest",
            "inference_test_status",
        )
    ):
        op.drop_column("model_records", column)
