"""Saved analysis, design, and contrast API contracts."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from transcriptforge_api.models.enums import AnalysisType

DimensionMethod = Literal["pca", "hierarchical_clustering", "umap", "tsne"]
DifferentialExpressionMethod = Literal["auto", "deseq2", "limma", "edger_ql", "limma_voom"]
SignatureScoringMethod = Literal[
    "mean_expression", "mean_z_score", "weighted_linear", "rank_based", "gsva", "ssgsea"
]
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


class EnrichmentParameters(BaseModel):
    enabled: bool = False
    collection_id: str = Field(
        default="transcriptforge_demo_effects",
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    ranking_metric: Literal["signed_log10_p_value"] = "signed_log10_p_value"
    permutation_count: int = Field(default=250, ge=100, le=5000)
    minimum_gene_set_size: int = Field(default=10, ge=2, le=5000)
    maximum_gene_set_size: int = Field(default=500, ge=2, le=10_000)

    @model_validator(mode="after")
    def validate_size_range(self) -> "EnrichmentParameters":
        if self.minimum_gene_set_size > self.maximum_gene_set_size:
            raise ValueError("Minimum gene-set size cannot exceed maximum gene-set size.")
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
    enrichment: EnrichmentParameters = Field(default_factory=EnrichmentParameters)

    @model_validator(mode="after")
    def validate_contrast_variable(self) -> "DifferentialExpressionParameters":
        if self.contrast.variable != self.design.primary_variable:
            raise ValueError("The contrast variable must match the primary design variable.")
        return self


class PhenotypeAssociationParameters(BaseModel):
    enabled: bool = False
    phenotype_column: VariableName | None = None
    phenotype_kind: Literal["auto", "categorical", "numeric"] = "auto"
    covariates: list[VariableName] = Field(default_factory=list, max_length=20)
    block_column: VariableName | None = None

    @model_validator(mode="after")
    def validate_terms(self) -> "PhenotypeAssociationParameters":
        if self.enabled and self.phenotype_column is None:
            raise ValueError("An enabled phenotype association requires a phenotype column.")
        terms = [*self.covariates]
        if self.block_column is not None:
            terms.append(self.block_column)
        if self.phenotype_column in terms:
            raise ValueError("The phenotype cannot also be a covariate or block column.")
        if len(terms) != len(set(terms)):
            raise ValueError("Association adjustment variables may only appear once.")
        return self


class SignatureScoringParameters(BaseModel):
    signature_mapping_id: str = Field(min_length=1, max_length=100)
    minimum_gene_set_size: int = Field(default=1, ge=1, le=5000)
    maximum_gene_set_size: int = Field(default=5000, ge=1, le=50_000)
    gsva_kcdf: Literal["auto", "Gaussian", "Poisson", "none"] = "Gaussian"
    gsva_tau: float = Field(default=1.0, gt=0, le=10)
    gsva_max_diff: bool = True
    gsva_abs_ranking: bool = False
    ssgsea_alpha: float = Field(default=0.25, gt=0, le=10)
    ssgsea_normalize: bool = True
    phenotype_association: PhenotypeAssociationParameters = Field(
        default_factory=PhenotypeAssociationParameters
    )

    @model_validator(mode="after")
    def validate_size_range(self) -> "SignatureScoringParameters":
        if self.minimum_gene_set_size > self.maximum_gene_set_size:
            raise ValueError("Minimum gene-set size cannot exceed maximum gene-set size.")
        return self


class AnalysisCreate(BaseModel):
    name: str = Field(default="Principal component analysis", min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    analysis_type: Literal[
        AnalysisType.DIMENSION_REDUCTION,
        AnalysisType.DIFFERENTIAL_EXPRESSION,
        AnalysisType.SIGNATURE,
    ] = AnalysisType.DIMENSION_REDUCTION
    method: DimensionMethod | DifferentialExpressionMethod | SignatureScoringMethod = "pca"
    assay: str = Field(default="log_expression", min_length=1, max_length=100)
    parameters: (
        DimensionReductionParameters | DifferentialExpressionParameters | SignatureScoringParameters
    ) = Field(default_factory=DimensionReductionParameters)
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
        elif analysis_type == AnalysisType.SIGNATURE.value:
            payload["method"] = payload.get("method", "mean_expression")
            payload["parameters"] = SignatureScoringParameters.model_validate(
                payload.get("parameters", {})
            )
            payload["name"] = payload.get("name", "Signature scoring")
        else:
            payload["parameters"] = DimensionReductionParameters.model_validate(
                payload.get("parameters", {})
            )
        return payload

    @model_validator(mode="after")
    def validate_type_specific_method(self) -> "AnalysisCreate":
        dimension_methods = {"pca", "hierarchical_clustering", "umap", "tsne"}
        de_methods = {"auto", "deseq2", "limma", "edger_ql", "limma_voom"}
        signature_methods = {
            "mean_expression",
            "mean_z_score",
            "weighted_linear",
            "rank_based",
            "gsva",
            "ssgsea",
        }
        if self.analysis_type == AnalysisType.DIMENSION_REDUCTION:
            if self.method not in dimension_methods or not isinstance(
                self.parameters, DimensionReductionParameters
            ):
                raise ValueError("Dimension reduction requires a dimension-reduction method.")
        elif self.analysis_type == AnalysisType.DIFFERENTIAL_EXPRESSION and (
            self.method not in de_methods
            or not isinstance(self.parameters, DifferentialExpressionParameters)
        ):
            raise ValueError("Differential expression requires a supported DE method.")
        elif self.analysis_type == AnalysisType.SIGNATURE and (
            self.method not in signature_methods
            or not isinstance(self.parameters, SignatureScoringParameters)
        ):
            raise ValueError("Signature scoring requires a supported scoring method.")
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
