"""Saved analysis, design, and contrast API contracts."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from transcriptforge_api.models.enums import AnalysisType

DimensionMethod = Literal["pca", "hierarchical_clustering", "umap", "tsne"]
DifferentialExpressionMethod = Literal["auto", "deseq2", "limma", "edger_ql", "limma_voom"]
VariableName = Annotated[
    str, StringConstraints(min_length=1, max_length=100, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
]


class DimensionReductionParameters(BaseModel):
    component_count: int = Field(default=10, ge=2, le=20)
    scale_features: bool = False
    top_variable_features: int = Field(default=500, ge=10, le=20_000)
    distance_metric: Literal["euclidean", "correlation"] = "correlation"
    linkage_method: Literal["average", "complete", "ward"] = "average"
    cluster_count: int = Field(default=4, ge=2, le=20)
    neighbors: int = Field(default=15, ge=2, le=200)
    min_distance: float = Field(default=0.2, ge=0, lt=1)
    perplexity: float = Field(default=15, ge=2, le=100)

    @model_validator(mode="after")
    def validate_linkage_distance(self) -> "DimensionReductionParameters":
        if self.linkage_method == "ward" and self.distance_metric != "euclidean":
            raise ValueError("Ward linkage requires Euclidean distance.")
        return self


class ContrastDefinition(BaseModel):
    variable: VariableName
    numerator: str = Field(min_length=1, max_length=200)
    denominator: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_distinct_levels(self) -> "ContrastDefinition":
        if self.numerator == self.denominator:
            raise ValueError("Contrast numerator and denominator must be different levels.")
        return self


class DesignSpecification(BaseModel):
    primary_variable: VariableName
    covariates: list[VariableName] = Field(default_factory=list, max_length=20)
    block_column: VariableName | None = None
    interaction_terms: list[tuple[VariableName, VariableName]] = Field(
        default_factory=list, max_length=10
    )
    reference_levels: dict[VariableName, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_terms(self) -> "DesignSpecification":
        terms = [self.primary_variable, *self.covariates]
        if self.block_column is not None:
            terms.append(self.block_column)
        if len(terms) != len(set(terms)):
            raise ValueError("Design variables may only appear once.")
        available = set(terms)
        for left, right in self.interaction_terms:
            if left == right or left not in available or right not in available:
                raise ValueError("Interaction terms must reference two distinct design variables.")
        return self


class DifferentialExpressionParameters(BaseModel):
    design: DesignSpecification
    contrast: ContrastDefinition
    low_count_threshold: int = Field(default=10, ge=0, le=1_000_000)
    minimum_samples: int = Field(default=2, ge=1, le=1000)
    fdr_threshold: float = Field(default=0.05, gt=0, le=1)
    absolute_log2_fold_change: float = Field(default=1.0, ge=0, le=100)
    independent_filtering: bool = True
    shrinkage: bool = True

    @model_validator(mode="after")
    def validate_contrast_variable(self) -> "DifferentialExpressionParameters":
        if self.contrast.variable != self.design.primary_variable:
            raise ValueError("The contrast variable must match the primary design variable.")
        return self


class AnalysisCreate(BaseModel):
    name: str = Field(default="Principal component analysis", min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    analysis_type: Literal[
        AnalysisType.DIMENSION_REDUCTION, AnalysisType.DIFFERENTIAL_EXPRESSION
    ] = AnalysisType.DIMENSION_REDUCTION
    method: DimensionMethod | DifferentialExpressionMethod = "pca"
    assay: str = Field(default="log_expression", min_length=1, max_length=100)
    parameters: DimensionReductionParameters | DifferentialExpressionParameters = Field(
        default_factory=DimensionReductionParameters
    )
    random_seed: int = Field(default=42, ge=0, le=2_147_483_647)

    @model_validator(mode="before")
    @classmethod
    def parse_type_specific_configuration(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        analysis_type = payload.get("analysis_type", AnalysisType.DIMENSION_REDUCTION.value)
        if analysis_type == AnalysisType.DIFFERENTIAL_EXPRESSION.value:
            payload["method"] = payload.get("method", "auto")
            payload["parameters"] = DifferentialExpressionParameters.model_validate(
                payload.get("parameters", {})
            )
            payload["name"] = payload.get("name", "Differential expression")
        else:
            payload["parameters"] = DimensionReductionParameters.model_validate(
                payload.get("parameters", {})
            )
        return payload

    @model_validator(mode="after")
    def validate_type_specific_method(self) -> "AnalysisCreate":
        dimension_methods = {"pca", "hierarchical_clustering", "umap", "tsne"}
        de_methods = {"auto", "deseq2", "limma", "edger_ql", "limma_voom"}
        if self.analysis_type == AnalysisType.DIMENSION_REDUCTION:
            if self.method not in dimension_methods or not isinstance(
                self.parameters, DimensionReductionParameters
            ):
                raise ValueError("Dimension reduction requires a dimension-reduction method.")
        elif self.method not in de_methods or not isinstance(
            self.parameters, DifferentialExpressionParameters
        ):
            raise ValueError("Differential expression requires a supported DE method.")
        return self


class DifferentialExpressionPreviewRequest(BaseModel):
    assay: str = Field(min_length=1, max_length=100)
    method: DifferentialExpressionMethod = "auto"
    parameters: DifferentialExpressionParameters


class MetadataVariableRead(BaseModel):
    name: str
    kind: Literal["categorical", "numeric"]
    levels: list[str]
    missing_count: int
    unique_count: int


class DesignOptionsRead(BaseModel):
    sample_count: int
    assays: list[str]
    variables: list[MetadataVariableRead]


class DesignCellRead(BaseModel):
    values: dict[str, str]
    sample_count: int


class DesignValidationRead(BaseModel):
    valid: bool
    formula: str
    resolved_method: str
    contrast_label: str
    sample_count: int
    contrast_counts: dict[str, int]
    design_matrix_columns: list[str]
    design_matrix_rank: int
    design_cells: list[DesignCellRead]
    errors: list[str]
    warnings: list[str]


class AnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    prepared_dataset_id: str
    analysis_type: AnalysisType
    name: str
    description: str | None
    configuration_json: dict[str, object]
    created_at: datetime
