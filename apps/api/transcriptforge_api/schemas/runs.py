"""Validation-run and artifact API contracts."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from transcriptforge_api.models.enums import RunState, RunType

DifferentialExpressionSort = Literal[
    "feature_id",
    "gene_symbol",
    "base_expression",
    "log2_fold_change",
    "standard_error",
    "statistic",
    "p_value",
    "adjusted_p_value",
    "significant",
]
SortDirection = Literal["asc", "desc"]


class DatasetValidationRequest(BaseModel):
    matrix_orientation: Literal["features_by_samples", "samples_by_features"] = (
        "features_by_samples"
    )
    feature_id_column: str = Field(default="gene_id", min_length=1, max_length=200)
    sample_id_column: str = Field(default="sample_id", min_length=1, max_length=200)
    feature_id_type: Literal[
        "ensembl_gene_id", "gene_symbol", "entrez_id", "probe_id", "transcript_id"
    ] = "ensembl_gene_id"
    strip_ensembl_version: bool = False


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_type: RunType
    dataset_id: str | None
    prepared_dataset_id: str | None
    analysis_id: str | None
    state: RunState
    profile: str
    nextflow_session_id: str | None
    nextflow_run_name: str | None
    exit_code: int | None
    error_summary: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class ArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    artifact_type: str
    title: str
    relative_path: str
    mime_type: str
    size_bytes: int
    sha256: str
    display_order: int
    metadata_json: dict[str, Any]


class DifferentialExpressionResultRow(BaseModel):
    feature_id: str
    gene_symbol: str | None = None
    base_expression: float | None = None
    log2_fold_change: float | None = None
    standard_error: float | None = None
    statistic: float | None = None
    p_value: float | None = None
    adjusted_p_value: float | None = None
    significant: bool
    contrast: str | None = None
    method: str | None = None


class DifferentialExpressionResultsPage(BaseModel):
    items: list[DifferentialExpressionResultRow]
    total: int
    offset: int
    limit: int
    base_expression_label: str


class ExpressionValue(BaseModel):
    sample_id: str
    value: float
    metadata: dict[str, str]


class ExpressionGroupSummary(BaseModel):
    level: str
    sample_count: int
    mean: float
    median: float
    minimum: float
    maximum: float


class FeatureExpressionProfile(BaseModel):
    assay: str
    source: str
    value_label: str
    contrast: dict[str, str]
    values: list[ExpressionValue]
    group_summaries: list[ExpressionGroupSummary]


class DifferentialExpressionFeatureDetail(BaseModel):
    result: DifferentialExpressionResultRow
    base_expression_label: str
    expression_profile: FeatureExpressionProfile | None = None
