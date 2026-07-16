"""Dataset and dataset-file API contracts."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from transcriptforge_api.models.enums import (
    DatasetModality,
    DatasetSourceKind,
    DatasetStatus,
)

SOURCE_COMPATIBILITY: dict[DatasetModality, set[DatasetSourceKind]] = {
    DatasetModality.BULK_RNASEQ: {
        DatasetSourceKind.FASTQ,
        DatasetSourceKind.COUNT_MATRIX,
        DatasetSourceKind.SALMON_QUANT,
    },
    DatasetModality.MICROARRAY: {
        DatasetSourceKind.AFFYMETRIX_CEL,
        DatasetSourceKind.NORMALIZED_MATRIX,
    },
    DatasetModality.GENERIC_EXPRESSION: {DatasetSourceKind.NORMALIZED_MATRIX},
}


class DatasetFileRole(StrEnum):
    FASTQ_R1 = "fastq_r1"
    FASTQ_R2 = "fastq_r2"
    COUNT_MATRIX = "count_matrix"
    ABUNDANCE_FILE = "abundance_file"
    CEL_FILE = "cel_file"
    EXPRESSION_MATRIX = "expression_matrix"
    SAMPLE_METADATA = "sample_metadata"
    PLATFORM_MANIFEST = "platform_manifest"
    TX2GENE = "tx2gene"
    GENE_SET = "gene_set"


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    modality: DatasetModality
    source_kind: DatasetSourceKind
    organism: Literal["Homo sapiens"] = "Homo sapiens"
    genome_build: str | None = Field(default="GRCh38", max_length=100)
    annotation_release: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_source_compatibility(self) -> "DatasetCreate":
        if self.source_kind not in SOURCE_COMPATIBILITY[self.modality]:
            raise ValueError(
                f"Source kind '{self.source_kind}' is not supported for modality '{self.modality}'."
            )
        return self


class DatasetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    annotation_release: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def require_change(self) -> "DatasetUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one dataset field must be supplied.")
        return self


class DatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    description: str | None
    modality: DatasetModality
    source_kind: DatasetSourceKind
    organism: str
    genome_build: str | None
    annotation_release: str | None
    status: DatasetStatus
    created_at: datetime
    updated_at: datetime


class DatasetFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    role: DatasetFileRole
    original_name: str
    storage_uri: str
    size_bytes: int
    sha256: str
    created_at: datetime


class PreparedDatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    version: int
    preparation_run_id: str | None
    value_types_available: list[str]
    sample_count: int
    feature_count: int
    qc_status: str
    created_at: datetime
