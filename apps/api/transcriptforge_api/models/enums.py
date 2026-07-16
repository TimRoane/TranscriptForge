"""Stable persisted domain values shared by models and API schemas."""

from enum import StrEnum


class DatasetModality(StrEnum):
    BULK_RNASEQ = "bulk_rnaseq"
    MICROARRAY = "microarray"
    GENERIC_EXPRESSION = "generic_expression"


class DatasetSourceKind(StrEnum):
    FASTQ = "fastq"
    COUNT_MATRIX = "count_matrix"
    SALMON_QUANT = "salmon_quant"
    AFFYMETRIX_CEL = "affymetrix_cel"
    NORMALIZED_MATRIX = "normalized_matrix"


class DatasetStatus(StrEnum):
    DRAFT = "draft"
    VALIDATING = "validating"
    VALID = "valid"
    INVALID = "invalid"
    PREPARING = "preparing"
    PREPARED = "prepared"


class RunType(StrEnum):
    DATASET_VALIDATION = "dataset_validation"
    DATASET_PREPARATION = "dataset_preparation"
    ANALYSIS = "analysis"
    PREDICTION = "prediction"


class RunState(StrEnum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"


class AnalysisType(StrEnum):
    DIFFERENTIAL_EXPRESSION = "differential_expression"
    DIMENSION_REDUCTION = "dimension_reduction"
    CLASSIFIER = "classifier"
    SIGNATURE = "signature"
    DECONVOLUTION = "deconvolution"
