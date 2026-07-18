"""Saved analysis, design, and contrast API contracts."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from transcriptforge_api.models.enums import AnalysisType

DimensionMethod = Literal["pca", "hierarchical_clustering", "umap", "tsne"]
DifferentialExpressionMethod = Literal["auto", "deseq2", "limma", "edger_ql", "limma_voom"]
SignatureScoringMethod = Literal[
    "mean_expression", "mean_z_score", "weighted_linear", "rank_based", "gsva", "ssgsea"
]
DeconvolutionMethod = Literal["epic", "quantiseq", "mcp_counter", "xcell"]
ClassifierMethod = Literal["elastic_net", "multinomial_elastic_net"]
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


class DeconvolutionParameters(BaseModel):
    reference_profile: str | None = Field(default=None, min_length=1, max_length=100)
    minimum_gene_overlap: float = Field(default=0.5, ge=0, le=1)
    tumor_mode: bool = False
    scale_mrna: bool = True


class ClassifierParameters(BaseModel):
    outcome_column: VariableName
    positive_class: str | None = Field(default=None, min_length=1, max_length=200)
    group_column: VariableName | None = None
    cohort_column: VariableName | None = None
    validation_mode: Literal["repeated_nested_cross_validation"] = (
        "repeated_nested_cross_validation"
    )
    feature_filter: Literal["top_variance"] = "top_variance"
    top_variable_features: int = Field(default=500, ge=10, le=20_000)
    class_weight: Literal["none", "balanced"] = "balanced"
    outer_folds: int = Field(default=5, ge=2, le=10)
    inner_folds: int = Field(default=4, ge=2, le=10)
    repeats: int = Field(default=3, ge=1, le=20)
    primary_metric: Literal[
        "roc_auc", "pr_auc", "balanced_accuracy", "macro_roc_auc", "macro_f1"
    ] = "roc_auc"
    probability_calibration: Literal["none", "sigmoid"] = "none"
    decision_threshold_strategy: Literal["fixed_0_5", "inner_cv_youden"] = "fixed_0_5"
    bootstrap_iterations: int = Field(default=1000, ge=200, le=5000)
    permutation_count: int = Field(default=100, ge=0, le=1000)

    @model_validator(mode="after")
    def validate_columns(self) -> "ClassifierParameters":
        columns = [self.outcome_column]
        if self.group_column is not None:
            columns.append(self.group_column)
        if self.cohort_column is not None:
            columns.append(self.cohort_column)
        if len(columns) != len(set(columns)):
            raise ValueError("Outcome, group, and cohort columns must be distinct.")
        return self


class DeconvolutionAssayOptionRead(BaseModel):
    name: str
    scales: list[Literal["linear", "log2", "variance_stabilized"]]
    value_types: list[Literal["nonnegative_continuous", "continuous"]]


class DeconvolutionInputRead(BaseModel):
    organism: Literal["Homo sapiens"]
    feature_level: Literal["gene"]
    identifier_namespace: Literal["gene_symbol"]
    assay_options: list[DeconvolutionAssayOptionRead]
    minimum_reference_overlap: float
    negative_values_permitted: bool


class DeconvolutionReferenceRead(BaseModel):
    id: str
    label: str


class DeconvolutionMethodRead(BaseModel):
    id: Literal["epic", "quantiseq", "mcp_counter", "xcell", "cibersortx_external"]
    display_name: str
    execution_mode: Literal["native", "external_import"]
    implementation_status: Literal[
        "runner_pending", "planned", "external_import_pending", "license_blocked", "available"
    ]
    result_type: Literal["cell_fraction", "enrichment_score"]
    quantity_label: str
    unit: Literal["fraction", "arbitrary_score"]
    composition_constraint: Literal[
        "bounded_sum", "sum_to_one_with_other", "not_compositional", "declared_by_import"
    ]
    within_sample_cell_type_comparison: bool
    between_sample_comparison: bool
    input: DeconvolutionInputRead
    references: list[DeconvolutionReferenceRead]
    default_reference: str | None
    interpretation: str
    source_url: str


class DeconvolutionRegistryRead(BaseModel):
    schema_version: Literal["1.0.0"]
    registry_version: str
    registry_sha256: str
    methods: list[DeconvolutionMethodRead]


class DeconvolutionMethodCapabilityRead(BaseModel):
    method: DeconvolutionMethodRead
    compatible_assays: list[str]
    configuration_available: bool
    execution_available: bool
    blocked_reasons: list[str]


class DeconvolutionCapabilitiesRead(BaseModel):
    prepared_dataset_id: str
    registry_version: str
    registry_sha256: str
    methods: list[DeconvolutionMethodCapabilityRead]


class DeconvolutionComparisonAssayRead(BaseModel):
    name: str
    scale: Literal["linear", "log2", "variance_stabilized"]
    value_type: Literal["nonnegative_continuous", "continuous"]
    feature_level: Literal["gene"]
    identifier_namespace: Literal["gene_symbol"]


class DeconvolutionComparisonReferenceRead(BaseModel):
    id: str
    version: str
    sha256: str


class DeconvolutionComparisonCellTypeRead(BaseModel):
    id: str
    label: str


class DeconvolutionComparisonEstimateRead(BaseModel):
    sample_id: str
    cell_type_id: str
    value: float


class DeconvolutionComparisonRunRead(BaseModel):
    analysis_id: str
    analysis_name: str
    run_id: str
    method: Literal["epic", "quantiseq", "mcp_counter", "xcell", "cibersortx_external"]
    display_name: str
    result_type: Literal["cell_fraction", "enrichment_score"]
    quantity_label: str
    unit: Literal["fraction", "arbitrary_score"]
    composition_constraint: Literal[
        "bounded_sum", "sum_to_one_with_other", "not_compositional", "declared_by_import"
    ]
    assay: DeconvolutionComparisonAssayRead
    reference: DeconvolutionComparisonReferenceRead
    reference_overlap_fraction: float = Field(ge=0, le=1)
    sample_ids: list[str]
    cell_types: list[DeconvolutionComparisonCellTypeRead]
    estimates: list[DeconvolutionComparisonEstimateRead]
    result_sha256: str
    method_registry_version: str
    method_registry_sha256: str


class DeconvolutionPairwiseCorrelationRead(BaseModel):
    left_run_id: str
    right_run_id: str
    left_method: str
    right_method: str
    cell_type_id: str
    cell_type_label: str
    sample_count: int = Field(ge=3)
    pearson_correlation: float = Field(ge=-1, le=1)


class DeconvolutionComparisonSectionRead(BaseModel):
    id: str
    result_type: Literal["cell_fraction", "enrichment_score"]
    unit: Literal["fraction", "arbitrary_score"]
    composition_constraints: list[
        Literal["bounded_sum", "sum_to_one_with_other", "not_compositional", "declared_by_import"]
    ]
    comparison_mode: Literal["fraction_pattern", "within_population_pattern"]
    assay: DeconvolutionComparisonAssayRead
    sample_ids: list[str]
    shared_cell_types: list[DeconvolutionComparisonCellTypeRead]
    reference_mode: Literal["method_specific_exact_population_intersection"]
    runs: list[DeconvolutionComparisonRunRead]
    correlations: list[DeconvolutionPairwiseCorrelationRead]
    warnings: list[str]


class DeconvolutionComparisonExclusionRead(BaseModel):
    analysis_id: str
    analysis_name: str
    run_id: str
    reason: str


class DeconvolutionComparisonRead(BaseModel):
    schema_version: Literal["1.0.0"]
    prepared_dataset_id: str
    latest_successful_run_count: int = Field(ge=0)
    sections: list[DeconvolutionComparisonSectionRead]
    exclusions: list[DeconvolutionComparisonExclusionRead]
    interpretation: str


class CibersortxSignatureRead(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    gene_count: int = Field(ge=1, le=1_000_000)

    @field_validator("name", "version")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized


class CibersortxRuntimeRead(BaseModel):
    version: str = Field(min_length=1, max_length=100)
    external_run_id: str = Field(min_length=1, max_length=200)
    executed_at: datetime

    @field_validator("version", "external_run_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized

    @field_validator("executed_at")
    @classmethod
    def validate_execution_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("External execution time must include a timezone.")
        if value.astimezone(UTC) > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("External execution time cannot be in the future.")
        return value


class CibersortxImportRequest(BaseModel):
    analysis_name: str = Field(
        default="CIBERSORTx relative fractions", min_length=1, max_length=200
    )
    assay: str = Field(default="tpm", min_length=1, max_length=100)
    mode: Literal["relative"]
    fractions_declared: bool
    batch_correction: Literal["none", "B-mode", "S-mode"] = "none"
    permutations: int = Field(default=0, ge=0, le=1_000_000)
    mixture_gene_count: int = Field(ge=1, le=10_000_000)
    overlap_gene_count: int = Field(ge=1, le=1_000_000)
    signature: CibersortxSignatureRead
    runtime: CibersortxRuntimeRead

    @field_validator("analysis_name", "assay")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank.")
        return normalized

    @model_validator(mode="after")
    def validate_external_declarations(self) -> "CibersortxImportRequest":
        if not self.fractions_declared:
            raise ValueError("CIBERSORTx values must be explicitly declared as relative fractions.")
        if self.overlap_gene_count > self.signature.gene_count:
            raise ValueError("Overlap gene count cannot exceed the signature gene count.")
        if self.overlap_gene_count > self.mixture_gene_count:
            raise ValueError("Overlap gene count cannot exceed the mixture gene count.")
        return self


class AnalysisCreate(BaseModel):
    name: str = Field(default="Principal component analysis", min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    analysis_type: Literal[
        AnalysisType.DIMENSION_REDUCTION,
        AnalysisType.DIFFERENTIAL_EXPRESSION,
        AnalysisType.SIGNATURE,
        AnalysisType.DECONVOLUTION,
        AnalysisType.CLASSIFIER,
    ] = AnalysisType.DIMENSION_REDUCTION
    method: (
        DimensionMethod
        | DifferentialExpressionMethod
        | SignatureScoringMethod
        | DeconvolutionMethod
        | ClassifierMethod
    ) = "pca"
    assay: str = Field(default="log_expression", min_length=1, max_length=100)
    parameters: (
        DimensionReductionParameters
        | DifferentialExpressionParameters
        | SignatureScoringParameters
        | DeconvolutionParameters
        | ClassifierParameters
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
            payload["method"] = payload.get("method", "mean_z_score")
            payload["parameters"] = SignatureScoringParameters.model_validate(
                payload.get("parameters", {})
            )
            payload["name"] = payload.get("name", "Signature scoring")
        elif analysis_type == AnalysisType.DECONVOLUTION.value:
            payload["method"] = payload.get("method", "epic")
            payload["assay"] = payload.get("assay", "tpm")
            payload["parameters"] = DeconvolutionParameters.model_validate(
                payload.get("parameters", {})
            )
            payload["name"] = payload.get("name", "Cell-type deconvolution")
        elif analysis_type == AnalysisType.CLASSIFIER.value:
            payload["method"] = payload.get("method", "elastic_net")
            payload["assay"] = payload.get("assay", "log_expression")
            payload["parameters"] = ClassifierParameters.model_validate(
                payload.get("parameters", {})
            )
            payload["name"] = payload.get("name", "Elastic-net classifier")
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
        deconvolution_methods = {"epic", "quantiseq", "mcp_counter", "xcell"}
        classifier_methods = {"elastic_net", "multinomial_elastic_net"}
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
        elif self.analysis_type == AnalysisType.DECONVOLUTION and (
            self.method not in deconvolution_methods
            or not isinstance(self.parameters, DeconvolutionParameters)
        ):
            raise ValueError("Deconvolution requires a registered native method.")
        elif self.analysis_type == AnalysisType.CLASSIFIER and (
            self.method not in classifier_methods
            or not isinstance(self.parameters, ClassifierParameters)
        ):
            raise ValueError("Classifier development requires a supported classifier method.")
        return self


class DifferentialExpressionPreviewRequest(BaseModel):
    assay: str = Field(min_length=1, max_length=100)
    method: DifferentialExpressionMethod = "auto"
    parameters: DifferentialExpressionParameters


class ClassifierPreviewRequest(BaseModel):
    assay: Literal["log_expression"] = "log_expression"
    method: ClassifierMethod = "elastic_net"
    parameters: ClassifierParameters
    random_seed: int = Field(default=42, ge=0, le=2_147_483_647)


class ClassifierFoldRead(BaseModel):
    repeat: int = Field(ge=1)
    fold: int = Field(ge=1)
    training_sample_count: int = Field(ge=1)
    test_sample_count: int = Field(ge=1)
    training_class_counts: dict[str, int]
    test_class_counts: dict[str, int]
    training_group_count: int = Field(ge=1)
    test_group_count: int = Field(ge=1)
    group_overlap_count: Literal[0]


class ClassifierDesignValidationRead(BaseModel):
    valid: bool
    method: ClassifierMethod
    assay: Literal["log_expression"]
    outcome_column: str
    negative_class: str | None
    positive_class: str | None
    class_labels: list[str]
    eligible_sample_count: int = Field(ge=0)
    class_counts: dict[str, int]
    group_column: str | None
    group_count: int = Field(ge=0)
    cohort_column: str | None
    outer_folds: int = Field(ge=2)
    inner_folds: int = Field(ge=2)
    repeats: int = Field(ge=1)
    expected_oof_prediction_count: int = Field(ge=0)
    preprocessing_scope: Literal["fit_inside_each_training_fold"]
    tuning_scope: Literal["inner_training_folds_only"]
    fold_plan: list[ClassifierFoldRead]
    errors: list[str]
    warnings: list[str]


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
