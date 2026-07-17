"""Dataset and dataset-file API contracts."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

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
    SAMPLE_SHEET = "sample_sheet"
    RAW_INGESTION_MANIFEST = "raw_ingestion_manifest"
    MICROARRAY_INGESTION_MANIFEST = "microarray_ingestion_manifest"


UPLOAD_ROLE_COMPATIBILITY: dict[DatasetSourceKind, set[DatasetFileRole]] = {
    DatasetSourceKind.FASTQ: {
        DatasetFileRole.FASTQ_R1,
        DatasetFileRole.FASTQ_R2,
        DatasetFileRole.SAMPLE_SHEET,
    },
    DatasetSourceKind.COUNT_MATRIX: {
        DatasetFileRole.COUNT_MATRIX,
        DatasetFileRole.SAMPLE_METADATA,
    },
    DatasetSourceKind.SALMON_QUANT: {
        DatasetFileRole.ABUNDANCE_FILE,
        DatasetFileRole.SAMPLE_SHEET,
        DatasetFileRole.TX2GENE,
    },
    DatasetSourceKind.AFFYMETRIX_CEL: {
        DatasetFileRole.CEL_FILE,
        DatasetFileRole.SAMPLE_METADATA,
        DatasetFileRole.PLATFORM_MANIFEST,
    },
    DatasetSourceKind.NORMALIZED_MATRIX: {
        DatasetFileRole.EXPRESSION_MATRIX,
        DatasetFileRole.SAMPLE_METADATA,
    },
}


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


class RawRNASeqIngestionRequest(BaseModel):
    reference_bundle_id: str = Field(
        default="gencode_v50_grch38_salmon_1_11_4",
        pattern=r"^[a-z][a-z0-9_]*$",
        max_length=128,
    )
    strandedness: Literal["auto", "unstranded", "forward", "reverse"] = "auto"


class RawRNASeqFileRead(BaseModel):
    dataset_file_id: str
    role: Literal["sample_sheet", "fastq_r1", "fastq_r2"]
    original_name: str
    storage_uri: str
    size_bytes: int
    sha256: str


class RawRNASeqLaneRead(BaseModel):
    lane_id: str
    read1: RawRNASeqFileRead
    read2: RawRNASeqFileRead | None


class RawRNASeqSampleRead(BaseModel):
    sample_id: str
    lanes: list[RawRNASeqLaneRead]
    metadata: dict[str, str]


class RawRNASeqReferenceRead(BaseModel):
    reference_id: str
    definition_sha256: str
    name: str
    annotation_release: str
    salmon_version: str


class RawRNASeqIngestionRead(BaseModel):
    schema_version: Literal["1.1.0"]
    dataset_id: str
    organism: Literal["Homo sapiens"]
    genome_build: str
    source_kind: Literal["fastq"]
    reference: RawRNASeqReferenceRead
    sample_sheet: RawRNASeqFileRead
    library_layout: Literal["single_end", "paired_end"]
    strandedness: Literal["auto", "unstranded", "forward", "reverse"]
    sample_count: int
    lane_count: int
    read_file_count: int
    samples: list[RawRNASeqSampleRead]
    warnings: list[str]


class ReferenceBundleCatalogRead(BaseModel):
    reference_id: str
    definition_sha256: str
    name: str
    organism: str
    genome_build: str
    annotation_provider: str
    annotation_release: int
    salmon_version: str
    index_strategy: str
    source_page: str
    assets: list[dict[str, Any]]


class MicroarrayIngestionRequest(BaseModel):
    platform_id: str = Field(
        default="affymetrix_hugene_1_0_st_v1",
        pattern=r"^[a-z][a-z0-9_]*$",
        max_length=128,
    )
    aggregation_method: Literal["highest_mad", "median", "mean"] = "highest_mad"


class MicroarrayFileRead(BaseModel):
    dataset_file_id: str
    role: Literal["cel_file", "sample_metadata"]
    original_name: str
    storage_uri: str
    size_bytes: int
    sha256: str


class MicroarrayPlatformSelectionRead(BaseModel):
    platform_id: str
    definition_sha256: str
    adapter_version: str
    vendor: Literal["Affymetrix"]
    array_design: str
    detected_chip_type: str
    cel_format: Literal["calvin", "xda"]
    normalization: dict[str, Any]
    annotation: dict[str, Any]


class MicroarraySampleRead(BaseModel):
    sample_id: str
    cel_file: MicroarrayFileRead
    metadata: dict[str, str]


class MicroarrayIngestionRead(BaseModel):
    schema_version: Literal["1.0.0"]
    dataset_id: str
    organism: Literal["Homo sapiens"]
    source_kind: Literal["affymetrix_cel"]
    platform: MicroarrayPlatformSelectionRead
    aggregation_method: Literal["highest_mad", "median", "mean"]
    sample_metadata: MicroarrayFileRead
    sample_count: int
    cel_file_count: int
    samples: list[MicroarraySampleRead]
    warnings: list[str]


class MicroarrayPlatformCatalogRead(BaseModel):
    platform_id: str
    definition_sha256: str
    adapter_version: str
    vendor: Literal["Affymetrix"]
    array_design: str
    organism: Literal["Homo sapiens"]
    chip_type_aliases: list[str]
    cel_formats: list[Literal["calvin", "xda"]]
    normalization: dict[str, Any]
    annotation: dict[str, Any]
    aggregation: dict[str, Any]
    sources: list[str]
