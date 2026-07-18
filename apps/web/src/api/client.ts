export type DatasetModality = 'bulk_rnaseq' | 'microarray' | 'generic_expression'
export type DatasetSourceKind =
  | 'fastq'
  | 'count_matrix'
  | 'salmon_quant'
  | 'affymetrix_cel'
  | 'normalized_matrix'

export interface HealthResponse {
  status: 'ok'
  service: 'transcriptforge-api'
  version: string
  environment: string
}

export interface Project {
  id: string
  name: string
  description: string | null
  owner_id: string
  created_at: string
  updated_at: string
}

export interface Dataset {
  id: string
  project_id: string
  name: string
  description: string | null
  modality: DatasetModality
  source_kind: DatasetSourceKind
  organism: 'Homo sapiens'
  genome_build: string | null
  annotation_release: string | null
  status: 'draft' | 'validating' | 'valid' | 'invalid' | 'preparing' | 'prepared'
  created_at: string
  updated_at: string
}

export interface DatasetFile {
  id: string
  dataset_id: string
  role: string
  original_name: string
  storage_uri: string
  size_bytes: number
  sha256: string
  created_at: string
}

export type DatasetFileRole =
  | 'count_matrix'
  | 'expression_matrix'
  | 'sample_metadata'
  | 'fastq_r1'
  | 'fastq_r2'
  | 'sample_sheet'
  | 'cel_file'
  | 'platform_manifest'

export interface RawRNASeqIngestion {
  schema_version: '1.0.0' | '1.1.0'
  dataset_id: string
  organism: 'Homo sapiens'
  genome_build: string
  source_kind: 'fastq'
  reference: {
    reference_id: string
    definition_sha256: string
    name: string
    annotation_release: string
    salmon_version: string
  }
  sample_sheet: RawRNASeqFile
  library_layout: 'single_end' | 'paired_end'
  strandedness: 'auto' | 'unstranded' | 'forward' | 'reverse'
  sample_count: number
  lane_count: number
  read_file_count: number
  samples: Array<{
    sample_id: string
    lanes: Array<{
      lane_id: string
      read1: RawRNASeqFile
      read2: RawRNASeqFile | null
    }>
    metadata: Record<string, string>
  }>
  warnings: string[]
}

export interface RawRNASeqFile {
  dataset_file_id: string
  role: 'sample_sheet' | 'fastq_r1' | 'fastq_r2'
  original_name: string
  storage_uri: string
  size_bytes: number
  sha256: string
}

export type MicroarrayAggregationMethod = 'highest_mad' | 'median' | 'mean'

export interface MicroarrayPlatformCatalog {
  platform_id: string
  definition_sha256: string
  adapter_version: string
  vendor: 'Affymetrix'
  array_design: string
  organism: 'Homo sapiens'
  chip_type_aliases: string[]
  cel_formats: Array<'calvin' | 'xda'>
  normalization: {
    engine: string
    method: string
    target: string
    pd_info_package: string
  }
  annotation: {
    package: string
    probe_key: string
    gene_id_field: string
    gene_symbol_field: string
    confidence: string
  }
  aggregation: {
    default_method: MicroarrayAggregationMethod
    supported_methods: MicroarrayAggregationMethod[]
  }
  sources: string[]
}

export interface MicroarrayFile {
  dataset_file_id: string
  role: 'cel_file' | 'sample_metadata'
  original_name: string
  storage_uri: string
  size_bytes: number
  sha256: string
}

export interface MicroarrayIngestion {
  schema_version: '1.0.0'
  dataset_id: string
  organism: 'Homo sapiens'
  source_kind: 'affymetrix_cel'
  platform: {
    platform_id: string
    definition_sha256: string
    adapter_version: string
    vendor: 'Affymetrix'
    array_design: string
    detected_chip_type: string
    cel_format: 'calvin' | 'xda'
    normalization: MicroarrayPlatformCatalog['normalization']
    annotation: MicroarrayPlatformCatalog['annotation']
  }
  aggregation_method: MicroarrayAggregationMethod
  sample_metadata: MicroarrayFile
  sample_count: number
  cel_file_count: number
  samples: Array<{
    sample_id: string
    cel_file: MicroarrayFile
    metadata: Record<string, string>
  }>
  warnings: string[]
}

export type RunState =
  | 'CREATED'
  | 'QUEUED'
  | 'STARTING'
  | 'RUNNING'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'CANCELLING'
  | 'CANCELLED'

export interface Run {
  id: string
  run_type: 'dataset_validation' | 'dataset_preparation' | 'analysis' | 'prediction'
  dataset_id: string | null
  prepared_dataset_id: string | null
  analysis_id: string | null
  state: RunState
  profile: string
  nextflow_session_id: string | null
  nextflow_run_name: string | null
  exit_code: number | null
  error_summary: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export interface ValidationFinding {
  severity: 'ERROR' | 'WARNING'
  code: string
  message: string
  location: string | null
  details: Record<string, unknown>
}

export interface ValidationReport {
  schema_version: '1.0.0'
  status: 'VALID' | 'INVALID'
  matrix: {
    orientation: 'features_by_samples' | 'samples_by_features'
    sample_count: number
    feature_count: number
  }
  metadata: { sample_count: number; column_count: number }
  findings: ValidationFinding[]
  suppressed_findings: Record<string, number>
  preview: {
    matrix_columns: string[]
    matrix_rows: Array<{ id: string; values: Record<string, string> }>
    metadata_rows: Array<Record<string, string>>
  }
}

export interface Artifact {
  id: string
  run_id: string
  artifact_type: string
  title: string
  relative_path: string
  mime_type: string
  size_bytes: number
  sha256: string
  display_order: number
  metadata_json: Record<string, unknown>
}

export interface DatasetValidationRequest {
  matrix_orientation?: 'features_by_samples' | 'samples_by_features'
  feature_id_column?: string
  sample_id_column?: string
  feature_id_type?: 'ensembl_gene_id' | 'gene_symbol' | 'entrez_id' | 'probe_id' | 'transcript_id'
  strip_ensembl_version?: boolean
}

export interface PreparedDataset {
  id: string
  dataset_id: string
  version: number
  preparation_run_id: string | null
  value_types_available: string[]
  sample_count: number
  feature_count: number
  qc_status: 'PASS' | 'REVIEW' | 'SEVERE_REVIEW'
  created_at: string
}

export interface QCSample {
  sample_id: string
  library_size: number
  detected_features: number
  detected_fraction: number
  zero_fraction: number
}

export interface MatrixQCSummary {
  status: 'PASS' | 'REVIEW' | 'SEVERE_REVIEW'
  samples: QCSample[]
  flags: Array<{ sample_id: string; status: 'PASS' | 'REVIEW'; reasons: string[] }>
}

export interface MicroarrayQCSummary {
  schema_version: '1.0.0'
  status: 'PASS' | 'REVIEW' | 'SEVERE_REVIEW'
  sample_count: number
  probe_count: number
  gene_count: number
  reviewed_sample_count: number
  plots: string[]
}

export type QCSummary = MatrixQCSummary | MicroarrayQCSummary

export interface FeatureMappingSummary {
  prepared_dataset_id: string
  prepared_version: number
  sample_count: number
  feature_count: number
  value_types_available: string[]
  qc_status: string
  mapped_feature_count: number
  unmapped_feature_count: number
  duplicate_group_count: number
  mapping_coverage: number
  probe_count?: number
  gene_count?: number
  aggregation_method?: MicroarrayAggregationMethod
  probe_mapping_path?: string
}

export type DimensionReductionMethod = 'pca' | 'hierarchical_clustering' | 'umap' | 'tsne'
export type DifferentialExpressionMethod = 'auto' | 'deseq2' | 'limma' | 'edger_ql' | 'limma_voom'

export interface DimensionReductionConfiguration {
  analysis_type: 'dimension_reduction'
  method: DimensionReductionMethod
  assay: string
  parameters: {
    component_count: number
    scale_features: boolean
    top_variable_features: number
    distance_metric: 'euclidean' | 'correlation'
    linkage_method: 'average' | 'complete' | 'ward'
    cluster_count: number
    neighbors: number
    min_distance: number
    perplexity: number
  }
  random_seed: number
}

export interface DifferentialExpressionParameters {
  design: {
    primary_variable: string
    covariates: string[]
    block_column: string | null
    interaction_terms: Array<[string, string]>
    reference_levels: Record<string, string>
  }
  contrast: { variable: string; numerator: string; denominator: string }
  low_count_threshold: number
  minimum_samples: number
  fdr_threshold: number
  absolute_log2_fold_change: number
  independent_filtering: boolean
  shrinkage: boolean
  enrichment: {
    enabled: boolean
    collection_id: string
    ranking_metric: 'signed_log10_p_value'
    permutation_count: number
    minimum_gene_set_size: number
    maximum_gene_set_size: number
  }
}

export interface DifferentialExpressionConfiguration {
  analysis_type: 'differential_expression'
  method: Exclude<DifferentialExpressionMethod, 'auto'>
  assay: string
  parameters: DifferentialExpressionParameters
  random_seed: number
  design_formula: string
  contrast_label: string
  design_validation: DesignValidation
}

export type SignatureScoringMethod =
  | 'mean_expression'
  | 'mean_z_score'
  | 'weighted_linear'
  | 'rank_based'
  | 'gsva'
  | 'ssgsea'

export interface SignatureScoringParameters {
  signature_mapping_id: string
  minimum_gene_set_size: number
  maximum_gene_set_size: number
  gsva_kcdf: 'auto' | 'Gaussian' | 'Poisson' | 'none'
  gsva_tau: number
  gsva_max_diff: boolean
  gsva_abs_ranking: boolean
  ssgsea_alpha: number
  ssgsea_normalize: boolean
  phenotype_association?: {
    enabled: boolean
    phenotype_column: string | null
    phenotype_kind: 'auto' | 'categorical' | 'numeric'
    covariates: string[]
    block_column: string | null
  }
}

export interface SignatureScoringConfiguration {
  analysis_type: 'signature'
  method: SignatureScoringMethod
  assay: 'log_expression'
  parameters: SignatureScoringParameters
  random_seed: number
  signature_mapping_report_sha256: string
  signature_definition_id: string
  mapping_coverage: number
}

export type DeconvolutionMethod = 'epic' | 'quantiseq' | 'mcp_counter' | 'xcell'
export type DeconvolutionResultType = 'cell_fraction' | 'enrichment_score'

export interface DeconvolutionMethodSpec {
  id: DeconvolutionMethod | 'cibersortx_external'
  display_name: string
  execution_mode: 'native' | 'external_import'
  implementation_status: 'runner_pending' | 'planned' | 'external_import_pending' | 'license_blocked' | 'available'
  result_type: DeconvolutionResultType
  quantity_label: string
  unit: 'fraction' | 'arbitrary_score'
  composition_constraint:
    | 'bounded_sum'
    | 'sum_to_one_with_other'
    | 'not_compositional'
    | 'declared_by_import'
  within_sample_cell_type_comparison: boolean
  between_sample_comparison: boolean
  input: {
    organism: 'Homo sapiens'
    feature_level: 'gene'
    identifier_namespace: 'gene_symbol'
    assay_options: Array<{
      name: string
      scales: Array<'linear' | 'log2' | 'variance_stabilized'>
      value_types: Array<'nonnegative_continuous' | 'continuous'>
    }>
    minimum_reference_overlap: number
    negative_values_permitted: boolean
  }
  references: Array<{ id: string; label: string }>
  default_reference: string | null
  interpretation: string
  source_url: string
}

export interface DeconvolutionCapabilities {
  prepared_dataset_id: string
  registry_version: string
  registry_sha256: string
  methods: Array<{
    method: DeconvolutionMethodSpec
    compatible_assays: string[]
    configuration_available: boolean
    execution_available: boolean
    blocked_reasons: string[]
  }>
}

export interface DeconvolutionConfiguration {
  analysis_type: 'deconvolution'
  method: DeconvolutionMethod
  assay: string
  parameters: {
    reference_profile: string
    minimum_gene_overlap: number
    tumor_mode: boolean
    scale_mrna: boolean
  }
  random_seed: number
  method_registry_version: string
  method_registry_sha256: string
  method_spec: DeconvolutionMethodSpec
  input_assay_descriptor: {
    name: string
    scale: 'linear' | 'log2' | 'variance_stabilized'
    value_type: string
    feature_level: 'gene'
    sha256: string
  }
  result_type: DeconvolutionResultType
  execution_available: boolean
}

export interface DeconvolutionResults {
  schema_version: '1.0.0'
  analysis_id: string
  prepared_dataset_id: string
  method: 'quantiseq'
  result_type: 'cell_fraction'
  quantity_label: string
  unit: 'fraction'
  composition_constraint: 'sum_to_one_with_other'
  input_validation: {
    input_feature_count: number
    mapped_feature_count: number
    blank_symbol_count: number
    duplicate_symbol_count: number
    reference_gene_count: number
    overlap_gene_count: number
    overlap_fraction: number
    minimum_overlap_fraction: number
    passed: boolean
  }
  reference: { id: string; version: string; sha256: string; cell_type_count: number }
  cell_types: Array<{ id: string; label: string; category?: string }>
  sample_ids: string[]
  estimates: Array<{ sample_id: string; cell_type_id: string; value: number }>
  composition_summaries: Array<{
    sample_id: string
    reported_sum: number
    residual_fraction: number
    within_tolerance: boolean
  }>
  warnings: string[]
  software: { language: string; language_version: string; packages: Record<string, string> }
  provenance: {
    expression_bundle_sha256: string
    analysis_request_sha256: string
    reference_sha256: string
  }
}

export interface Analysis {
  id: string
  project_id: string
  prepared_dataset_id: string
  analysis_type: 'dimension_reduction' | 'differential_expression' | 'signature' | 'deconvolution'
  name: string
  description: string | null
  configuration_json:
    | DimensionReductionConfiguration
    | DifferentialExpressionConfiguration
    | SignatureScoringConfiguration
    | DeconvolutionConfiguration
  created_at: string
}

export interface CreateDimensionReductionRequest {
  name?: string
  description?: string
  analysis_type?: 'dimension_reduction'
  method?: DimensionReductionMethod
  assay?: string
  parameters?: Partial<DimensionReductionConfiguration['parameters']>
  random_seed?: number
}

export interface DesignOptions {
  sample_count: number
  assays: string[]
  variables: Array<{
    name: string
    kind: 'categorical' | 'numeric'
    levels: string[]
    missing_count: number
    unique_count: number
  }>
}

export interface DifferentialExpressionPreviewRequest {
  assay: string
  method: DifferentialExpressionMethod
  parameters: Partial<DifferentialExpressionParameters> & Pick<DifferentialExpressionParameters, 'design' | 'contrast'>
}

export interface DesignValidation {
  valid: boolean
  formula: string
  resolved_method: string
  contrast_label: string
  sample_count: number
  contrast_counts: Record<string, number>
  design_matrix_columns: string[]
  design_matrix_rank: number
  design_cells: Array<{ values: Record<string, string>; sample_count: number }>
  errors: string[]
  warnings: string[]
}

export interface CreateDifferentialExpressionRequest extends DifferentialExpressionPreviewRequest {
  name?: string
  description?: string
  analysis_type: 'differential_expression'
  random_seed?: number
}

export interface PCAPlot {
  schema_version: '1.0.0'
  analysis_id: string
  axes: Array<{ component: string; explained_variance_ratio: number }>
  points: Array<{
    sample_id: string
    coordinates: Record<string, number>
    metadata: Record<string, string>
  }>
}

export interface VariancePlot {
  schema_version: '1.0.0'
  components: Array<{
    component: string
    explained_variance: number
    explained_variance_ratio: number
  }>
}

export interface ResultManifest {
  schema_version: '1.0.0'
  analysis_type: string
  title: string
  summary_metrics: Array<{ label: string; value: string | number | boolean | null }>
  warnings: string[]
}

export interface DifferentialExpressionPlot {
  schema_version: '1.0.0'
  analysis_id: string
  x_label: string
  y_label: string
  points: Array<{
    feature_id: string
    x: number | null
    y: number | null
    adjusted_p_value: number | null
    significant: boolean
  }>
}

export interface PValueDistribution {
  schema_version: '1.0.0'
  analysis_id: string
  bin_width: number
  finite_p_value_count: number
  missing_p_value_count: number
  bins: Array<{ start: number; end: number; count: number }>
}

export interface ExpressionHeatmap {
  schema_version: '1.0.0'
  analysis_id: string
  assay: string
  scale: 'feature_z_score'
  source: string
  sample_ordering: string
  feature_ids: string[]
  sample_ids: string[]
  values: number[][]
  metadata: Record<string, Record<string, string>>
  feature_annotations: Record<string, {
    log2_fold_change: number | null
    adjusted_p_value: number | null
    significant: boolean
  }>
  contrast: { variable: string; numerator: string; denominator: string }
}

export type DifferentialExpressionSort =
  | 'feature_id'
  | 'gene_symbol'
  | 'base_expression'
  | 'log2_fold_change'
  | 'standard_error'
  | 'statistic'
  | 'p_value'
  | 'adjusted_p_value'
  | 'significant'

export interface DifferentialExpressionResultRow {
  feature_id: string
  gene_symbol: string | null
  base_expression: number | null
  log2_fold_change: number | null
  standard_error: number | null
  statistic: number | null
  p_value: number | null
  adjusted_p_value: number | null
  significant: boolean
  contrast: string | null
  method: string | null
}

export interface DifferentialExpressionResultQuery {
  search?: string
  fdrMax?: number
  absoluteLog2FoldChangeMin?: number
  significantOnly?: boolean
  sortBy?: DifferentialExpressionSort
  direction?: 'asc' | 'desc'
  offset?: number
  limit?: number
}

export interface DifferentialExpressionResultsPage {
  items: DifferentialExpressionResultRow[]
  total: number
  offset: number
  limit: number
  base_expression_label: string
}

export interface DifferentialExpressionFeatureDetail {
  result: DifferentialExpressionResultRow
  base_expression_label: string
  expression_profile: null | {
    assay: string
    source: string
    value_label: string
    contrast: { variable: string; numerator: string; denominator: string }
    values: Array<{ sample_id: string; value: number; metadata: Record<string, string> }>
    group_summaries: Array<{
      level: string
      sample_count: number
      mean: number
      median: number
      minimum: number
      maximum: number
    }>
  }
}

export interface GeneSignature {
  id: string
  project_id: string
  prepared_dataset_id: string
  source_analysis_id: string
  source_run_id: string
  name: string
  description: string | null
  status: 'draft'
  feature_ids: string[]
  feature_snapshot_json: DifferentialExpressionResultRow[]
  selection_json: Record<string, unknown>
  created_at: string
  updated_at: string
  research_use_warning: string
}

export interface SignatureDefinition {
  id: string
  project_id: string
  name: string
  description: string | null
  definition_format: 'gene_list' | 'gmt'
  identifier_type: 'ensembl_gene_id' | 'gene_symbol' | 'entrez_id'
  original_name: string
  source_sha256: string
  source_size_bytes: number
  manifest_sha256: string
  set_count: number
  requested_identifier_count: number
  unique_identifier_count: number
  duplicate_identifier_count: number
  weighted: boolean
  created_at: string
  updated_at: string
}

export interface SignatureMappingReport {
  schema_version: '1.0.0'
  signature_definition_id: string
  prepared_dataset_id: string
  signature_definition_sha256: string
  expression_bundle_sha256: string
  identifier_type: SignatureDefinition['identifier_type']
  strip_ensembl_version: boolean
  set_count: number
  requested_identifier_count: number
  unique_identifier_count: number
  mapped_identifier_count: number
  missing_identifier_count: number
  ambiguous_identifier_count: number
  duplicate_identifier_count: number
  mapping_coverage: number
  sets: Array<{
    signature_id: string
    name: string
    requested_identifier_count: number
    unique_identifier_count: number
    mapped_identifier_count: number
    missing_identifier_count: number
    ambiguous_identifier_count: number
    duplicate_identifier_count: number
    mapping_coverage: number
    mapped_entries: Array<{ identifier: string; feature_id: string; weight?: number }>
    mapped_feature_ids: string[]
    missing_identifiers: string[]
    ambiguous_identifiers: string[]
  }>
}

export interface SignatureMappingRecord {
  id: string
  signature_definition_id: string
  prepared_dataset_id: string
  report_sha256: string
  missing_sha256: string
  ambiguous_sha256: string
  requested_identifier_count: number
  unique_identifier_count: number
  mapped_identifier_count: number
  missing_identifier_count: number
  ambiguous_identifier_count: number
  duplicate_identifier_count: number
  mapping_coverage: number
  report_json: SignatureMappingReport
  created_at: string
  updated_at: string
}

export interface SignatureScores {
  schema_version: '1.1.0'
  analysis_id: string
  prepared_dataset_id: string
  method: SignatureScoringMethod
  assay: 'log_expression'
  formula: string
  signature_mapping: {
    id: string
    report_sha256: string
    signature_definition_id: string
    signature_definition_sha256: string
    expression_bundle_sha256: string
    mapping_coverage: number
    requested_identifier_count: number
    mapped_identifier_count: number
    missing_identifier_count: number
    ambiguous_identifier_count: number
    duplicate_identifier_count: number
  }
  sample_count: number
  set_count: number
  sets: Array<{
    signature_id: string
    name: string
    requested_identifier_count: number
    mapped_identifier_count: number
    scored_feature_count: number
    excluded_constant_feature_count: number
    mapping_coverage: number
    score_minimum: number
    score_maximum: number
    score_mean: number
    scores: Array<{
      sample_id: string
      score: number
      metadata: Record<string, string>
    }>
  }>
  phenotype_association?: null | {
    phenotype_column: string
    phenotype_kind: 'categorical' | 'numeric'
    covariates: string[]
    block_column: string | null
    formula: string
    design_matrix_columns: string[]
    associations: Array<{
      signature_id: string
      signature_name: string
      test: 'adjusted_linear_regression' | 'adjusted_two_group_comparison' | 'adjusted_omnibus_group_comparison'
      sample_count: number
      effect: number | null
      statistic: number
      degrees_of_freedom: number
      p_value: number
      adjusted_p_value: number
      correlation: number | null
      group_summaries: Array<{
        level: string
        sample_count: number
        score_mean: number
      }>
    }>
  }
  warnings: string[]
  software: {
    language: string
    language_version: string
    implementation: string
    packages: Record<string, string>
  }
}

export interface EnrichmentResult {
  gene_set_id: string
  gene_set_name: string
  direction: 'up' | 'down' | 'mixed'
  set_size: number
  overlap_size: number
  enrichment_score: number | null
  normalized_enrichment_score: number | null
  odds_ratio: number | null
  p_value: number
  adjusted_p_value: number
  leading_edge: string[]
  significant: boolean
}

export interface EnrichmentSummary {
  schema_version: '1.0.0'
  analysis_id: string
  collection: {
    collection_id: string
    name: string
    version: string
    identifier_namespace: string
    source: string
    license: string
    gmt_sha256: string
    set_count: number
  }
  source_result: {
    method: string
    contrast: string
    result_sha256: string
    tested_feature_count: number
    significant_feature_count: number
  }
  parameters: {
    identifier_field: 'feature_id'
    ranking_metric: 'signed_log10_p_value'
    random_seed: number
    permutation_count: number
    minimum_gene_set_size: number
    maximum_gene_set_size: number
    fdr_threshold: number
    absolute_log2_fold_change: number
  }
  ranked_list: EnrichmentResult[]
  over_representation: EnrichmentResult[]
  warnings: string[]
}

export interface CreateGeneSignatureRequest {
  name: string
  description?: string
  feature_ids: string[]
  selection: {
    mode: 'manual'
    search?: string
    fdr_max?: number
    absolute_log2_fold_change_min?: number
    significant_only: boolean
    sort_by: DifferentialExpressionSort
    direction: 'asc' | 'desc'
  }
}

export interface EmbeddingPlot {
  schema_version: '1.0.0'
  analysis_id: string
  method: 'umap' | 'tsne'
  axes: string[]
  points: PCAPlot['points']
}

export interface DendrogramPlot {
  schema_version: '1.0.0'
  analysis_id: string
  sample_order: string[]
  icoord: number[][]
  dcoord: number[][]
  color_list: string[]
  clusters: Record<string, number>
  metadata: Record<string, Record<string, string>>
}

export interface CorrelationHeatmap {
  schema_version: '1.0.0'
  sample_order: string[]
  values: number[][]
  metadata: Record<string, Record<string, string>>
}

export interface CreateDatasetRequest {
  name: string
  description?: string
  modality: DatasetModality
  source_kind: DatasetSourceKind
  genome_build?: string
  annotation_release?: string
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, init)
  if (!response.ok) {
    let message = `Request failed with status ${response.status}`
    try {
      const payload = (await response.json()) as { detail?: string | Array<{ msg: string }> }
      if (typeof payload.detail === 'string') message = payload.detail
      if (Array.isArray(payload.detail)) message = payload.detail.map((item) => item.msg).join(' ')
    } catch {
      // Preserve the status-based fallback when the response is not JSON.
    }
    throw new ApiError(message, response.status)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request('/health', { signal })
}

export function fetchProjects(signal?: AbortSignal): Promise<Project[]> {
  return request('/projects', { signal })
}

export function fetchProject(projectId: string, signal?: AbortSignal): Promise<Project> {
  return request(`/projects/${projectId}`, { signal })
}

export function createProject(payload: { name: string; description?: string }): Promise<Project> {
  return request('/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function deleteProject(projectId: string): Promise<void> {
  return request(`/projects/${projectId}`, { method: 'DELETE' })
}

export function fetchDatasets(projectId: string, signal?: AbortSignal): Promise<Dataset[]> {
  return request(`/projects/${projectId}/datasets`, { signal })
}

export function fetchDataset(datasetId: string, signal?: AbortSignal): Promise<Dataset> {
  return request(`/datasets/${datasetId}`, { signal })
}

export function createDataset(
  projectId: string,
  payload: CreateDatasetRequest,
): Promise<Dataset> {
  return request(`/projects/${projectId}/datasets`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function uploadDatasetFile(
  datasetId: string,
  role: DatasetFileRole,
  file: File,
): Promise<DatasetFile> {
  const form = new FormData()
  form.append('role', role)
  form.append('file', file)
  return request(`/datasets/${datasetId}/files`, { method: 'POST', body: form })
}

export function fetchDatasetFiles(
  datasetId: string,
  signal?: AbortSignal,
): Promise<DatasetFile[]> {
  return request(`/datasets/${datasetId}/files`, { signal })
}

export function ingestRawRNASeq(
  datasetId: string,
  payload: {
    reference_bundle_id?: string
    strandedness: 'auto' | 'unstranded' | 'forward' | 'reverse'
  },
): Promise<RawRNASeqIngestion> {
  return request(`/datasets/${datasetId}/raw-rnaseq/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchRawRNASeqIngestion(
  datasetId: string,
  signal?: AbortSignal,
): Promise<RawRNASeqIngestion | null> {
  return request(`/datasets/${datasetId}/raw-rnaseq/ingestion`, { signal })
}

export function fetchMicroarrayPlatforms(
  signal?: AbortSignal,
): Promise<MicroarrayPlatformCatalog[]> {
  return request('/microarray-platforms', { signal })
}

export function ingestMicroarray(
  datasetId: string,
  payload: {
    platform_id: string
    aggregation_method: MicroarrayAggregationMethod
  },
): Promise<MicroarrayIngestion> {
  return request(`/datasets/${datasetId}/microarray/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchMicroarrayIngestion(
  datasetId: string,
  signal?: AbortSignal,
): Promise<MicroarrayIngestion | null> {
  return request(`/datasets/${datasetId}/microarray/ingestion`, { signal })
}

export function validateDataset(
  datasetId: string,
  payload: DatasetValidationRequest = {},
): Promise<Run> {
  return request(`/datasets/${datasetId}/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchValidationRuns(datasetId: string, signal?: AbortSignal): Promise<Run[]> {
  return request(`/datasets/${datasetId}/validation-runs`, { signal })
}

export function fetchRun(runId: string, signal?: AbortSignal): Promise<Run> {
  return request(`/runs/${runId}`, { signal })
}

export function cancelRun(runId: string): Promise<Run> {
  return request(`/runs/${runId}/cancel`, { method: 'POST' })
}

export function fetchValidationReport(runId: string, signal?: AbortSignal): Promise<ValidationReport> {
  return request(`/runs/${runId}/validation-report`, { signal })
}

export function fetchRunArtifacts(runId: string, signal?: AbortSignal): Promise<Artifact[]> {
  return request(`/runs/${runId}/artifacts`, { signal })
}

export function artifactDownloadUrl(artifactId: string): string {
  return `${apiBaseUrl}/artifacts/${artifactId}/download`
}

export function prepareDataset(datasetId: string): Promise<Run> {
  return request(`/datasets/${datasetId}/prepare`, { method: 'POST' })
}

export function fetchPreparationRuns(datasetId: string, signal?: AbortSignal): Promise<Run[]> {
  return request(`/datasets/${datasetId}/preparation-runs`, { signal })
}

export function fetchPreparedVersions(
  datasetId: string,
  signal?: AbortSignal,
): Promise<PreparedDataset[]> {
  return request(`/datasets/${datasetId}/prepared-versions`, { signal })
}

export function fetchPreparedDataset(
  preparedDatasetId: string,
  signal?: AbortSignal,
): Promise<PreparedDataset> {
  return request(`/prepared-datasets/${preparedDatasetId}`, { signal })
}

export function fetchQCSummary(runId: string, signal?: AbortSignal): Promise<QCSummary> {
  return request(`/runs/${runId}/qc-summary`, { signal })
}

export function fetchFeatureMappingSummary(
  runId: string,
  signal?: AbortSignal,
): Promise<FeatureMappingSummary> {
  return request(`/runs/${runId}/feature-mapping-summary`, { signal })
}

export function createDimensionReductionAnalysis(
  preparedDatasetId: string,
  payload: CreateDimensionReductionRequest,
): Promise<Analysis> {
  return request(`/prepared-datasets/${preparedDatasetId}/analyses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchDesignOptions(
  preparedDatasetId: string,
  signal?: AbortSignal,
): Promise<DesignOptions> {
  return request(`/prepared-datasets/${preparedDatasetId}/differential-expression/design-options`, { signal })
}

export function validateDifferentialExpressionDesign(
  preparedDatasetId: string,
  payload: DifferentialExpressionPreviewRequest,
  signal?: AbortSignal,
): Promise<DesignValidation> {
  return request(`/prepared-datasets/${preparedDatasetId}/differential-expression/validate-design`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
}

export function createDifferentialExpressionAnalysis(
  preparedDatasetId: string,
  payload: CreateDifferentialExpressionRequest,
): Promise<Analysis> {
  return request(`/prepared-datasets/${preparedDatasetId}/analyses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function createSignatureScoringAnalysis(
  preparedDatasetId: string,
  payload: {
    name: string
    method: SignatureScoringMethod
    signatureMappingId: string
    parameters?: Partial<Omit<SignatureScoringParameters, 'signature_mapping_id'>>
  },
): Promise<Analysis> {
  return request(`/prepared-datasets/${preparedDatasetId}/analyses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: payload.name,
      analysis_type: 'signature',
      method: payload.method,
      assay: 'log_expression',
      parameters: {
        signature_mapping_id: payload.signatureMappingId,
        ...payload.parameters,
      },
      random_seed: 0,
    }),
  })
}

export function fetchDeconvolutionCapabilities(
  preparedDatasetId: string,
  signal?: AbortSignal,
): Promise<DeconvolutionCapabilities> {
  return request(`/prepared-datasets/${preparedDatasetId}/deconvolution/methods`, { signal })
}

export function fetchDeconvolutionResults(
  runId: string,
  signal?: AbortSignal,
): Promise<DeconvolutionResults> {
  return request(`/runs/${runId}/deconvolution-results`, { signal })
}

export function createDeconvolutionAnalysis(
  preparedDatasetId: string,
  payload: {
    name: string
    method: DeconvolutionMethod
    assay: string
    referenceProfile: string
    minimumGeneOverlap: number
    tumorMode?: boolean
    scaleMrna?: boolean
  },
): Promise<Analysis> {
  return request(`/prepared-datasets/${preparedDatasetId}/analyses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: payload.name,
      analysis_type: 'deconvolution',
      method: payload.method,
      assay: payload.assay,
      parameters: {
        reference_profile: payload.referenceProfile,
        minimum_gene_overlap: payload.minimumGeneOverlap,
        tumor_mode: payload.tumorMode ?? false,
        scale_mrna: payload.scaleMrna ?? true,
      },
      random_seed: 0,
    }),
  })
}

export function fetchPreparedAnalyses(
  preparedDatasetId: string,
  signal?: AbortSignal,
): Promise<Analysis[]> {
  return request(`/prepared-datasets/${preparedDatasetId}/analyses`, { signal })
}

export function fetchAnalysis(analysisId: string, signal?: AbortSignal): Promise<Analysis> {
  return request(`/analyses/${analysisId}`, { signal })
}

export function runAnalysis(analysisId: string): Promise<Run> {
  return request(`/analyses/${analysisId}/run`, { method: 'POST' })
}

export function fetchAnalysisRuns(analysisId: string, signal?: AbortSignal): Promise<Run[]> {
  return request(`/analyses/${analysisId}/runs`, { signal })
}

export function fetchPCAPlot(runId: string, signal?: AbortSignal): Promise<PCAPlot> {
  return request(`/runs/${runId}/pca-plot`, { signal })
}

export function fetchVariancePlot(runId: string, signal?: AbortSignal): Promise<VariancePlot> {
  return request(`/runs/${runId}/variance-plot`, { signal })
}

export function fetchResultManifest(
  runId: string,
  signal?: AbortSignal,
): Promise<ResultManifest> {
  return request(`/runs/${runId}/result-manifest`, { signal })
}

export function fetchEmbeddingPlot(runId: string, signal?: AbortSignal): Promise<EmbeddingPlot> {
  return request(`/runs/${runId}/embedding-plot`, { signal })
}

export function fetchDendrogramPlot(
  runId: string,
  signal?: AbortSignal,
): Promise<DendrogramPlot> {
  return request(`/runs/${runId}/dendrogram-plot`, { signal })
}

export function fetchCorrelationHeatmap(
  runId: string,
  signal?: AbortSignal,
): Promise<CorrelationHeatmap> {
  return request(`/runs/${runId}/correlation-heatmap`, { signal })
}

export function fetchVolcanoPlot(
  runId: string,
  signal?: AbortSignal,
): Promise<DifferentialExpressionPlot> {
  return request(`/runs/${runId}/volcano-plot`, { signal })
}

export function fetchMAPlot(
  runId: string,
  signal?: AbortSignal,
): Promise<DifferentialExpressionPlot> {
  return request(`/runs/${runId}/ma-plot`, { signal })
}

export function fetchPValueDistribution(
  runId: string,
  signal?: AbortSignal,
): Promise<PValueDistribution> {
  return request(`/runs/${runId}/p-value-distribution`, { signal })
}

export function fetchExpressionHeatmap(
  runId: string,
  signal?: AbortSignal,
): Promise<ExpressionHeatmap> {
  return request(`/runs/${runId}/expression-heatmap`, { signal })
}

export function fetchEnrichmentSummary(
  runId: string,
  signal?: AbortSignal,
): Promise<EnrichmentSummary> {
  return request(`/runs/${runId}/enrichment-summary`, { signal })
}

export function fetchSignatureScores(
  runId: string,
  signal?: AbortSignal,
): Promise<SignatureScores> {
  return request(`/runs/${runId}/signature-scores`, { signal })
}

function differentialExpressionResultParams(
  query: DifferentialExpressionResultQuery,
): URLSearchParams {
  const params = new URLSearchParams()
  if (query.search?.trim()) params.set('search', query.search.trim())
  if (query.fdrMax !== undefined) params.set('fdr_max', String(query.fdrMax))
  if (query.absoluteLog2FoldChangeMin !== undefined) {
    params.set('absolute_log2_fold_change_min', String(query.absoluteLog2FoldChangeMin))
  }
  if (query.significantOnly) params.set('significant_only', 'true')
  if (query.sortBy) params.set('sort_by', query.sortBy)
  if (query.direction) params.set('direction', query.direction)
  if (query.offset !== undefined) params.set('offset', String(query.offset))
  if (query.limit !== undefined) params.set('limit', String(query.limit))
  return params
}

export function fetchDifferentialExpressionResults(
  runId: string,
  query: DifferentialExpressionResultQuery,
  signal?: AbortSignal,
): Promise<DifferentialExpressionResultsPage> {
  const params = differentialExpressionResultParams(query)
  return request(`/runs/${runId}/differential-expression/results?${params}`, { signal })
}

export function filteredDifferentialExpressionDownloadUrl(
  runId: string,
  query: DifferentialExpressionResultQuery,
): string {
  const params = differentialExpressionResultParams(query)
  params.delete('offset')
  params.delete('limit')
  return `${apiBaseUrl}/runs/${runId}/differential-expression/results.tsv?${params}`
}

export function fetchDifferentialExpressionFeature(
  runId: string,
  featureId: string,
  signal?: AbortSignal,
): Promise<DifferentialExpressionFeatureDetail> {
  return request(
    `/runs/${runId}/differential-expression/features/${encodeURIComponent(featureId)}`,
    { signal },
  )
}

export function fetchRunSignatures(
  runId: string,
  signal?: AbortSignal,
): Promise<GeneSignature[]> {
  return request(`/runs/${runId}/signatures`, { signal })
}

export function createGeneSignature(
  runId: string,
  payload: CreateGeneSignatureRequest,
): Promise<GeneSignature> {
  return request(`/runs/${runId}/signatures`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchSignatureDefinitions(
  projectId: string,
  signal?: AbortSignal,
): Promise<SignatureDefinition[]> {
  return request(`/projects/${projectId}/signature-definitions`, { signal })
}

export function uploadSignatureDefinition(
  projectId: string,
  payload: {
    name: string
    description?: string
    definitionFormat: SignatureDefinition['definition_format']
    identifierType: SignatureDefinition['identifier_type']
    file: File
  },
): Promise<SignatureDefinition> {
  const form = new FormData()
  form.append('name', payload.name)
  if (payload.description) form.append('description', payload.description)
  form.append('definition_format', payload.definitionFormat)
  form.append('identifier_type', payload.identifierType)
  form.append('file', payload.file)
  return request(`/projects/${projectId}/signature-definitions`, {
    method: 'POST',
    body: form,
  })
}

export function mapSignatureDefinition(
  definitionId: string,
  preparedDatasetId: string,
): Promise<SignatureMappingRecord> {
  return request(
    `/signature-definitions/${definitionId}/map/${preparedDatasetId}`,
    { method: 'POST' },
  )
}

export function fetchSignatureMappings(
  preparedDatasetId: string,
  signal?: AbortSignal,
): Promise<SignatureMappingRecord[]> {
  return request(`/prepared-datasets/${preparedDatasetId}/signature-mappings`, { signal })
}

export function signatureMappingDownloadUrl(
  mappingId: string,
  document: 'report.json' | 'missing.tsv' | 'ambiguous.tsv',
): string {
  return `${apiBaseUrl}/signature-mappings/${mappingId}/${document}`
}
