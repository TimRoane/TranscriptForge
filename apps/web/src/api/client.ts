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
  deployment_mode: 'single_user_local'
}

export interface Project {
  id: string
  name: string
  description: string | null
  owner_id: string
  created_at: string
  updated_at: string
}

export type AssayLifecycleStage =
  | 'DEFINE'
  | 'FEASIBILITY'
  | 'EXPLORE'
  | 'OPTIMIZE'
  | 'DEVELOP'
  | 'LOCK'
  | 'VALIDATE'
  | 'REPORT'
  | 'ON_HOLD'
  | 'COMPLETED'

export type AssayReadinessStatus =
  | 'NOT_ASSESSED'
  | 'BLOCKED'
  | 'NEEDS_INFORMATION'
  | 'READY_FOR_RECOMMENDED_ACTION'
  | 'ACTION_IN_PROGRESS'
  | 'REVIEW_REQUIRED'

export interface AssayProject {
  id: string
  project_id: string
  name: string
  proposed_purpose: string | null
  specimen_type: string | null
  biological_context: string | null
  proposed_output: string | null
  current_stage: AssayLifecycleStage
  readiness_status: AssayReadinessStatus
  active_question_id: string | null
  assay_version: string | null
  created_by: string
  created_at: string
  updated_at: string
  completed_at: string | null
}

export interface QuestionCatalogEntry {
  key: string
  question: string
  stage: AssayLifecycleStage
  experiment_type?: string | null
  analysis_type?: string | null
  study_type?: string | null
  required_inputs: string[]
  required_metadata: string[]
  recommended_endpoints: string[]
  design_checks: string[]
  possible_next_actions: string[]
}

export interface QuestionCatalog {
  schema_version: '1.0.0'
  catalog_version: string
  questions: QuestionCatalogEntry[]
}

export interface ScientificQuestion {
  id: string
  assay_project_id: string
  question_key: string
  plain_language_question: string
  formal_question: string
  stage: AssayLifecycleStage
  status: 'OPEN' | 'RESOLVED' | 'SUPERSEDED'
  source: 'USER_SELECTED' | 'SYSTEM_RECOMMENDED' | 'FOLLOW_UP_FROM_RESULT'
  created_at: string
  resolved_at: string | null
  resolution_summary: string | null
}

export interface ReadinessItem {
  rule_id: string
  facts: Record<string, unknown>
  conclusion: string
  severity: 'INFO' | 'WARNING' | 'BLOCKER'
  suggested_action: string
  assumptions: string[]
  documentation_url: string
}

export interface AssayReadiness {
  schema_version: '1.0.0'
  stage: AssayLifecycleStage
  status: AssayReadinessStatus
  evaluated_at: string
  ready_items: ReadinessItem[]
  missing_items: ReadinessItem[]
  blockers: ReadinessItem[]
  warnings: ReadinessItem[]
  recommended_action_ids: string[]
  alternative_action_ids: string[]
  not_recommended_action_ids: string[]
}

export interface Recommendation {
  id: string
  assay_project_id: string
  source_type: string
  source_id: string
  rule_id: string
  recommendation_type: string
  title: string
  summary: string
  why: string
  what_it_resolves: string
  stage: AssayLifecycleStage
  priority: number
  requirement_level: 'BLOCKER' | 'STRONGLY_RECOMMENDED' | 'RECOMMENDED' | 'OPTIONAL' | 'NOT_RECOMMENDED'
  status: 'OPEN' | 'ACCEPTED' | 'REJECTED' | 'MODIFIED' | 'SUPERSEDED' | 'COMPLETED'
  required_inputs: string[]
  expected_output: string
  proposed_action: Record<string, unknown>
  evidence_refs: Array<Record<string, unknown>>
  assumptions: string[]
  limitations: string[]
  alternative_action_ids: string[]
  scientist_decision_required: true
  created_at: string
  resolved_at: string | null
}

export interface DecisionRecord {
  id: string
  assay_project_id: string
  source_type: string
  source_id: string
  stage: AssayLifecycleStage
  decision_key: string
  decision: string
  rationale: string
  selected_option: string
  alternatives: Array<Record<string, unknown>>
  evidence_refs: Array<Record<string, unknown>>
  made_by: string
  made_at: string
  supersedes_decision_id: string | null
}

export interface GuidanceResult {
  id: string
  assay_project_id: string
  question_id: string
  analysis_id: string
  run_id: string
  payload_json: {
    schema_version: '1.0.0'
    analysis_type: string
    question_answered: string
    important_findings: string[]
    quality_warnings: string[]
    unresolved_risks: string[]
    recommended_next_actions: string[]
    evidence_refs: Array<{ artifact_type: string; path: string; sha256: string }>
    scientist_decision_required: true
  }
  artifact_uri: string
  artifact_sha256: string
  created_at: string
}

export interface ModelRecord {
  id: string
  analysis_id: string
  run_id: string
  model_name: string
  algorithm: string
  outcome_column: string
  metrics_json: Record<string, unknown>
  feature_count: number
  status: 'CANDIDATE' | 'REVIEWED' | 'LOCKED' | 'RETIRED' | 'SUPERSEDED'
  reviewed_at: string | null
  reviewed_by: string | null
  locked_at: string | null
  locked_by: string | null
  retired_at: string | null
  parent_model_id: string | null
  model_manifest_sha256: string | null
  model_package_sha256: string | null
  feature_schema_sha256: string | null
  preprocessing_sha256: string | null
  model_object_sha256: string | null
  threshold_sha256: string | null
  training_dataset_refs_json: Array<Record<string, unknown>>
  validation_dataset_refs_json: Array<Record<string, unknown>>
  container_digest: string | null
  inference_test_status: string
  created_at: string
}

export interface ModelLockReadiness {
  model_id: string
  ready: boolean
  checks: Record<string, boolean>
  blockers: string[]
  warnings: string[]
}

export interface ModelIntegrity {
  model_id: string
  valid: boolean
  checks: Record<string, boolean>
  errors: string[]
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
  run_type: 'dataset_validation' | 'dataset_preparation' | 'analysis' | 'prediction' | 'assay_experiment' | 'assay_study'
  dataset_id: string | null
  prepared_dataset_id: string | null
  analysis_id: string | null
  experiment_id?: string | null
  study_id?: string | null
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

export interface ClassifierParameters {
  outcome_column: string
  positive_class: string | null
  group_column: string | null
  cohort_column: string | null
  validation_mode: 'repeated_nested_cross_validation'
  feature_filter: 'top_variance'
  top_variable_features: number
  class_weight: 'none' | 'balanced'
  outer_folds: number
  inner_folds: number
  repeats: number
  primary_metric: 'roc_auc' | 'pr_auc' | 'balanced_accuracy' | 'macro_roc_auc' | 'macro_f1'
  probability_calibration: 'none' | 'sigmoid'
  decision_threshold_strategy: 'fixed_0_5' | 'inner_cv_youden'
  bootstrap_iterations: number
  permutation_count: number
}

export interface ClassifierFold {
  repeat: number
  fold: number
  training_sample_count: number
  test_sample_count: number
  training_class_counts: Record<string, number>
  test_class_counts: Record<string, number>
  training_group_count: number
  test_group_count: number
  group_overlap_count: 0
}

export interface ClassifierDesignValidation {
  valid: boolean
  method: 'elastic_net' | 'multinomial_elastic_net'
  assay: 'log_expression'
  outcome_column: string
  negative_class: string | null
  positive_class: string | null
  class_labels: string[]
  eligible_sample_count: number
  class_counts: Record<string, number>
  group_column: string | null
  group_count: number
  cohort_column: string | null
  outer_folds: number
  inner_folds: number
  repeats: number
  expected_oof_prediction_count: number
  preprocessing_scope: 'fit_inside_each_training_fold'
  tuning_scope: 'inner_training_folds_only'
  fold_plan: ClassifierFold[]
  errors: string[]
  warnings: string[]
}

export interface ClassifierConfiguration {
  analysis_type: 'classifier'
  method: 'elastic_net' | 'multinomial_elastic_net'
  assay: 'log_expression'
  parameters: ClassifierParameters
  random_seed: number
  design_validation: ClassifierDesignValidation
  execution_available: boolean
  leakage_policy: {
    preprocessing_scope: 'fit_inside_each_training_fold'
    feature_selection_scope: 'fit_inside_each_training_fold'
    hyperparameter_tuning_scope: 'inner_training_folds_only'
    outer_test_fold_role: 'evaluation_only'
  }
}

export interface ClassifierResults {
  schema_version: '1.0.0'
  analysis_id: string
  prepared_dataset_id: string
  method: 'elastic_net'
  assay: 'log_expression'
  outcome: {
    column: string
    negative_class: string
    positive_class: string
    class_counts: Record<string, number>
  }
  validation: {
    mode: 'repeated_nested_cross_validation'
    group_column: string | null
    cohort_column: string | null
    outer_folds: number
    inner_folds: number
    repeats: number
    primary_metric: string
    probability_calibration: string
    decision_threshold_strategy: string
  }
  sample_count: number
  input_feature_count: number
  top_variable_features: number
  oof_coverage: {
    expected_prediction_count: number
    observed_prediction_count: number
    one_prediction_per_sample_per_repeat: true
  }
  metrics: Record<string, number>
  repeat_metrics: Array<Record<string, number> & { repeat: number }>
  confidence_intervals: {
    method: 'experimental_unit_percentile_bootstrap'
    iterations: number
    confidence_level: 0.95
    intervals: Record<string, { lower: number; upper: number }>
  }
  diagnostic_curves: {
    roc_curve: Array<{ false_positive_rate: number; true_positive_rate: number; threshold: number | null }>
    precision_recall_curve: Array<{ recall: number; precision: number; threshold: number | null }>
    calibration_curve: Array<{ predicted_probability: number; observed_fraction: number; sample_count: number }>
    calibration_intercept: number
    calibration_slope: number
    confusion_matrix: Record<string, number>
  }
  permutation_control: {
    method: 'full_nested_cross_validation_label_permutation'
    count: number
    roc_auc_values: number[]
    mean_roc_auc?: number
    empirical_p_value: number | null
    note?: string
  }
  learning_curve: Array<{
    training_fraction: number
    mean_roc_auc: number
    fold_roc_auc: number[]
  }>
  model_comparisons: Array<{
    method: 'elastic_net' | 'random_forest' | 'hist_gradient_boosting'
    role: 'primary_locked_model' | 'comparison_only_not_exported'
    metrics: Record<string, number>
    tuning_scope: 'inner_training_folds_only'
    best_parameters_by_outer_fold?: Array<Record<string, unknown>>
  }>
  folds: Array<ClassifierFold & {
    selected_feature_count: number
    nonzero_feature_count: number
    best_c: number
    best_l1_ratio: number
    decision_threshold: number
  }>
  feature_stability: Array<{
    feature_id: string
    selection_frequency: number
    nonzero_frequency: number
    mean_coefficient: number
  }>
  leakage_audit: Record<string, string | boolean>
  locked_model: {
    path: 'model.json'
    feature_schema_path: 'inference_schema.json'
    model_card_path: 'model_card.json'
    inference_example_path: 'inference_example.tsv'
  }
  warnings: string[]
}

export interface MulticlassClassifierResults {
  schema_version: '1.0.0'
  analysis_id: string
  prepared_dataset_id: string
  method: 'multinomial_elastic_net'
  assay: 'log_expression'
  outcome: {
    column: string
    classes: string[]
    class_counts: Record<string, number>
  }
  validation: {
    mode: 'repeated_nested_cross_validation'
    group_column: string | null
    cohort_column: string | null
    outer_folds: number
    inner_folds: number
    repeats: number
    primary_metric: 'macro_roc_auc' | 'macro_f1' | 'balanced_accuracy'
    prediction_rule: 'maximum_class_probability'
  }
  sample_count: number
  input_feature_count: number
  top_variable_features: number
  oof_coverage: {
    expected_prediction_count: number
    observed_prediction_count: number
    one_prediction_per_sample_per_repeat: true
  }
  metrics: Record<string, number>
  repeat_metrics: Array<Record<string, number> & { repeat: number }>
  confidence_intervals: {
    method: 'experimental_unit_percentile_bootstrap'
    iterations: number
    confidence_level: 0.95
    intervals: Record<string, { lower: number; upper: number }>
  }
  diagnostics: {
    one_vs_rest_roc_curves: Record<string, Array<{
      false_positive_rate: number
      true_positive_rate: number
    }>>
    confusion_matrix: number[][]
    class_order: string[]
  }
  permutation_control: {
    method: 'full_nested_cross_validation_label_permutation'
    count: number
    macro_roc_auc_values: number[]
    mean_macro_roc_auc: number | null
    empirical_p_value: number | null
  }
  folds: Array<ClassifierFold & {
    selected_feature_count: number
    nonzero_coefficient_count: number
    best_c: number
    best_l1_ratio: number
  }>
  feature_stability: Array<{
    feature_id: string
    class_label: string
    selection_frequency: number
    nonzero_frequency: number
    mean_coefficient: number
  }>
  leakage_audit: Record<string, string | boolean>
  locked_model: ClassifierResults['locked_model']
  warnings: string[]
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
  method: DeconvolutionMethod | 'cibersortx_external'
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
  external_import?: CibersortxImportProvenance
}

export interface DeconvolutionResults {
  schema_version: '1.0.0'
  analysis_id: string
  prepared_dataset_id: string
  method: 'quantiseq' | 'mcp_counter' | 'xcell' | 'cibersortx_external'
  method_registry_version: string
  method_registry_sha256: string
  result_type: DeconvolutionResultType
  quantity_label: string
  unit: 'fraction' | 'arbitrary_score'
  composition_constraint: 'sum_to_one_with_other' | 'not_compositional' | 'declared_by_import'
  input_validation: {
    assay: string
    scale: 'linear' | 'log2' | 'variance_stabilized'
    value_type: string
    feature_level: 'gene'
    identifier_namespace: 'gene_symbol'
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
  composition_summaries?: Array<{
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
    external_source_sha256?: string
  }
  external_import?: CibersortxImportProvenance
}

export interface CibersortxImportProvenance {
  source_filename: string
  source_sha256: string
  source_size_bytes: number
  mode: 'relative'
  values_declared_as: 'relative_fraction'
  batch_correction: 'none' | 'B-mode' | 'S-mode'
  permutations: number
  signature: { name: string; version: string; sha256: string; gene_count: number }
  runtime: {
    platform: 'CIBERSORTx'
    version: string
    external_run_id: string
    executed_at: string
  }
}

export interface CibersortxImportMetadata {
  analysis_name: string
  assay: string
  mode: 'relative'
  fractions_declared: true
  batch_correction: 'none' | 'B-mode' | 'S-mode'
  permutations: number
  mixture_gene_count: number
  overlap_gene_count: number
  signature: CibersortxImportProvenance['signature']
  runtime: Omit<CibersortxImportProvenance['runtime'], 'platform'>
}

export interface DeconvolutionComparisonRun {
  analysis_id: string
  analysis_name: string
  run_id: string
  method: DeconvolutionMethod | 'cibersortx_external'
  display_name: string
  result_type: DeconvolutionResultType
  quantity_label: string
  unit: 'fraction' | 'arbitrary_score'
  composition_constraint:
    | 'bounded_sum'
    | 'sum_to_one_with_other'
    | 'not_compositional'
    | 'declared_by_import'
  assay: {
    name: string
    scale: 'linear' | 'log2' | 'variance_stabilized'
    value_type: 'nonnegative_continuous' | 'continuous'
    feature_level: 'gene'
    identifier_namespace: 'gene_symbol'
  }
  reference: { id: string; version: string; sha256: string }
  reference_overlap_fraction: number
  sample_ids: string[]
  cell_types: Array<{ id: string; label: string }>
  estimates: Array<{ sample_id: string; cell_type_id: string; value: number }>
  result_sha256: string
  method_registry_version: string
  method_registry_sha256: string
}

export interface DeconvolutionComparison {
  schema_version: '1.0.0'
  prepared_dataset_id: string
  latest_successful_run_count: number
  sections: Array<{
    id: string
    result_type: DeconvolutionResultType
    unit: 'fraction' | 'arbitrary_score'
    composition_constraints: Array<
      'bounded_sum' | 'sum_to_one_with_other' | 'not_compositional' | 'declared_by_import'
    >
    comparison_mode: 'fraction_pattern' | 'within_population_pattern'
    assay: DeconvolutionComparisonRun['assay']
    sample_ids: string[]
    shared_cell_types: Array<{ id: string; label: string }>
    reference_mode: 'method_specific_exact_population_intersection'
    runs: DeconvolutionComparisonRun[]
    correlations: Array<{
      left_run_id: string
      right_run_id: string
      left_method: string
      right_method: string
      cell_type_id: string
      cell_type_label: string
      sample_count: number
      pearson_correlation: number
    }>
    warnings: string[]
  }>
  exclusions: Array<{
    analysis_id: string
    analysis_name: string
    run_id: string
    reason: string
  }>
  interpretation: string
}

export interface Analysis {
  id: string
  project_id: string
  prepared_dataset_id: string
  assay_project_id: string | null
  scientific_question_id: string | null
  analysis_type:
    | 'dimension_reduction'
    | 'differential_expression'
    | 'signature'
    | 'deconvolution'
    | 'classifier'
  name: string
  description: string | null
  configuration_json:
    | DimensionReductionConfiguration
    | DifferentialExpressionConfiguration
    | SignatureScoringConfiguration
    | DeconvolutionConfiguration
    | ClassifierConfiguration
  created_at: string
}

export interface GuidedAnalysisContext {
  assay_project_id: string
  scientific_question_id: string
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

export interface ExperimentInputOption {
  prepared_dataset_id: string
  dataset_id: string
  dataset_name: string
  prepared_version: number
  sample_count: number
  feature_count: number
  assays: string[]
  qc_status: string
}

export interface ExperimentDesignOptions {
  prepared_dataset_id: string
  sample_count: number
  assays: string[]
  measurement_ids: string[]
  metadata_columns: string[]
  metadata_rows: Array<Record<string, string>>
}

export interface ExperimentAssignment {
  measurement_id: string
  biological_sample_id: string
  prepared_dataset_id: string
  include: boolean
  exclusion_reason: string | null
  replicate_id: string | null
  pair_id: string | null
  input_ng: number | null
  dv200: number | null
  sequencing_run: string | null
  condition: string | null
  run: string | null
  quality_metric: number | null
  operator: string | null
  reagent_lot: string | null
  instrument: string | null
  processing_order: number | null
  extraction_method: string | null
  library_method: string | null
  sequencing_depth: number | null
  specimen_group: string | null
  technical_failure: boolean
}

export interface ExperimentDesignFinding {
  severity: 'ERROR' | 'WARNING' | 'INFO'
  code: string
  message: string
  facts: Record<string, unknown>
  recommendation: string
}

export interface ExperimentDesignValidation {
  schema_version: '1.0.0'
  valid: boolean
  retrospective_mapping: boolean
  measurement_count: number
  biological_sample_count: number
  included_measurement_count: number
  reference_level?: number
  input_levels?: number[]
  reference_condition?: string
  comparator_condition?: string
  conditions?: string[]
  complete_pair_count?: number
  factors?: string[]
  interactions?: string[]
  factor_levels?: Record<string, string[]>
  design_matrix_rank?: number
  design_matrix_columns?: number
  residual_degrees_of_freedom?: number
  run_levels?: string[]
  specimen_groups?: string[]
  findings: ExperimentDesignFinding[]
  errors: ExperimentDesignFinding[]
  warnings: ExperimentDesignFinding[]
  informational: ExperimentDesignFinding[]
}

export interface DevelopmentExperiment {
  id: string
  assay_project_id: string
  question_id: string
  prepared_dataset_id: string
  parent_experiment_id: string | null
  name: string
  experiment_type: 'TECHNICAL_FEASIBILITY' | 'INPUT_DEGRADATION_EXPLORATION' | 'PAIRED_CONDITION_COMPARISON' | 'MULTIFACTOR_OPTIMIZATION'
  objective: string
  mode: 'PLAN_FIRST' | 'ANALYZE_EXISTING'
  status: 'DRAFT' | 'DESIGN_VALID' | 'DESIGN_INVALID' | 'LOCKED_FOR_EXECUTION' | 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED' | 'SUPERSEDED'
  experiment_spec: Record<string, unknown>
  experiment_spec_uri: string | null
  experiment_spec_sha256: string | null
  assignments: ExperimentAssignment[]
  assignments_uri: string | null
  assignments_sha256: string | null
  design_validation: ExperimentDesignValidation | null
  development_bundle_uri: string | null
  current_revision: number
  created_by: string
  created_at: string
  updated_at: string
  locked_at: string | null
  completed_at: string | null
}

export interface ExperimentCreatePayload {
  assay_project_id: string
  question_id: string
  prepared_dataset_id: string
  name: string
  objective: string
  experiment_type: 'TECHNICAL_FEASIBILITY' | 'INPUT_DEGRADATION_EXPLORATION' | 'PAIRED_CONDITION_COMPARISON' | 'MULTIFACTOR_OPTIMIZATION'
  mode: 'PLAN_FIRST' | 'ANALYZE_EXISTING'
  reference_level?: number
  reference_condition?: string
  comparator_condition?: string
  assay: string
  primary_endpoints: string[]
  secondary_endpoints: string[]
  declared_questions: string[]
  reference_level_rationale?: string
  condition_contrast_rationale?: string
  endpoint_rationale: string
  assignments: ExperimentAssignment[]
  factor_names?: string[]
  interactions?: string[]
}

export interface ExperimentResults {
  experiment_id: string
  status: string
  run_id: string | null
  decision_summary: null | {
    schema_version: string
    question: string
    finding: string
    evidence: Array<Record<string, unknown>>
    limitations: string[]
    criteria_mode: string
    condition_results: Array<Record<string, unknown>>
    recommended_next_action_ids: string[]
    scientist_decision_required: true
  }
  recommendations: null | { schema_version: string; recommendations: Array<Record<string, unknown>> }
  artifacts: Array<Pick<Artifact, 'id' | 'artifact_type' | 'title' | 'relative_path' | 'mime_type' | 'size_bytes' | 'sha256'>>
}

export interface StudyAssignment {
  measurement_id: string
  biological_sample_id: string
  replicate_id: string | null
  operator: string | null
  run: string | null
  reagent_lot: string | null
  input_level: number | null
  quality_metric: number | null
  qc_failure: boolean
  condition: string | null
  challenge_type: string | null
  subgroup: string | null
  instrument: string | null
  day: string | null
  site: string | null
  include: boolean
  exclusion_reason: string | null
}

export interface AcceptanceCriterionInput {
  key: string
  metric: 'icc' | 'categorical_agreement' | 'repeatability_sd' | 'reproducibility_sd' | 'mean_absolute_score_difference' | 'call_agreement_to_reference' | 'qc_failure_rate' | 'paired_bias' | 'discordance_rate' | 'profile_correlation' | 'tost_equivalence' | 'mean_challenge_effect' | 'call_change_rate'
  endpoint: 'classifier_score' | 'predicted_class' | 'qc_failure'
  operator: 'gt' | 'gte' | 'lt' | 'lte' | 'between' | 'absolute_lte' | 'all_levels' | 'consecutive_levels'
  threshold: number | number[]
  rationale: string
}

export interface StudyDesignValidation {
  schema_version: '1.0.0'
  valid: boolean
  included_measurement_count: number
  biological_sample_count: number
  replicates_per_sample: Record<string, number>
  reference_level?: number
  ordered_levels?: number[]
  complete_pair_count?: number
  factor_levels: Record<string, string[]>
  design_matrix_rank: number
  design_matrix_columns: number
  errors: Array<{ code: string; message: string; facts?: Record<string, unknown> }>
  warnings: Array<{ code: string; message: string; facts?: Record<string, unknown> }>
}

export interface AnalyticalStudy {
  id: string
  assay_project_id: string
  question_id: string
  model_id: string
  prepared_dataset_id: string
  parent_study_id: string | null
  name: string
  study_type: 'PRECISION_REPRODUCIBILITY' | 'INPUT_DEGRADATION_LIMIT' | 'PAIRED_BRIDGING' | 'ROBUSTNESS_INTERFERENCE'
  objective: string
  status: 'DRAFT' | 'DESIGN_VALID' | 'DESIGN_INVALID' | 'LOCKED' | 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED' | 'SUPERSEDED'
  study_spec_json: Record<string, unknown>
  assignments_json: StudyAssignment[]
  criteria_json: AcceptanceCriterionInput[]
  design_validation_json: StudyDesignValidation | null
  study_spec_uri: string | null
  study_spec_sha256: string | null
  assignments_uri: string | null
  assignments_sha256: string | null
  validation_bundle_uri: string | null
  current_revision: number
  created_by: string
  created_at: string
  updated_at: string
  locked_at: string | null
  completed_at: string | null
}

export interface StudyInputOptions {
  locked_models: Array<{
    id: string
    name: string
    algorithm: string
    expected_assay: string
    feature_count: number
    manifest_sha256: string
  }>
  prepared_datasets: Array<{
    id: string
    dataset_name: string
    version: number
    sample_count: number
    feature_count: number
    assays: string[]
    qc_status: string
  }>
}

export interface StudyCreatePayload {
  assay_project_id: string
  question_id: string
  model_id: string
  prepared_dataset_id: string
  name: string
  objective: string
  study_type: 'PRECISION_REPRODUCIBILITY' | 'INPUT_DEGRADATION_LIMIT' | 'PAIRED_BRIDGING' | 'ROBUSTNESS_INTERFERENCE'
  assignments: StudyAssignment[]
  factors: string[]
  criteria: AcceptanceCriterionInput[]
  confidence_level: number
  bootstrap_iterations: number
  threshold_proximity_band: number
  reference_level?: number
  level_rationale?: string
  reference_condition?: string
  comparator_condition?: string
  equivalence_margin?: number
  condition_rationale?: string
}

export interface StudyResults {
  study_id: string
  status: string
  run_id: string | null
  summary: null | {
    overall_status: 'PASS' | 'FAIL' | 'INDETERMINATE'
    finding: string
    limitations: string[]
    model_retrained: false
    scientist_decision_required: true
    precision?: Record<string, number | null | Record<string, number>>
    variance_components?: Record<string, number | string | null>
    agreement?: {
      categorical_agreement: number | null
      per_sample_call_stability: Array<Record<string, unknown>>
    }
    input_degradation?: {
      levels: Array<Record<string, unknown>>
      trend: Record<string, unknown>
      change_point_exploration: Record<string, unknown>
      threshold_stability: Record<string, unknown>
      candidate_lowest_tested_level: number | null
      candidate_interpretation: string
    }
    paired_bridging?: {
      pair_count: number
      paired_bias: number
      paired_bias_confidence_interval_95: { lower: number; upper: number }
      profile_correlation: number | null
      correlation_passes_equivalence: false
      categorical_agreement: number
      discordance_rate: number
      tost_equivalence: { margin: number; passed: boolean; method: string }
      subgroup_review: Array<Record<string, unknown>>
      threshold_adjacent_review: Record<string, unknown>
    }
    robustness_interference?: {
      pair_count: number
      mean_challenge_effect: number
      challenge_effect_confidence_interval_95: { lower: number; upper: number }
      maximum_effect_margin: number
      effect_within_margin: boolean
      call_change_rate: number
      qc_failure_rate: number
      challenge_type_review: Array<Record<string, unknown>>
      threshold_adjacent_review: Record<string, unknown>
      biological_specificity_claims_supported: false
    }
    threshold_stability: {
      decision_threshold: number
      proximity_band: number
      near_threshold_count: number
      near_threshold_measurement_ids: string[]
    }
    acceptance_results: {
      overall_status: 'PASS' | 'FAIL' | 'INDETERMINATE'
      criteria: Array<AcceptanceCriterionInput & {
        observed: unknown
        status: 'PASS' | 'FAIL' | 'INDETERMINATE' | 'NOT_APPLICABLE'
        population: string
        uncertainty: unknown
      }>
    }
  }
  artifacts: Array<Pick<Artifact, 'id' | 'artifact_type' | 'title' | 'relative_path' | 'mime_type' | 'size_bytes' | 'sha256'>>
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

export interface ClassifierPreviewRequest {
  assay: 'log_expression'
  method: 'elastic_net' | 'multinomial_elastic_net'
  parameters: ClassifierParameters
  random_seed: number
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

export interface ClassifierExternalValidationArtifact {
  name: string
  title: string
  filename: string
  mime_type: string
  size_bytes: number
  sha256: string
}

export interface ClassifierExternalValidation {
  id: string
  project_id: string
  name: string
  description: string | null
  development_accession: string
  external_accession: string
  protocol_id: string
  status: 'SUCCESS_CRITERIA_MET' | 'SUCCESS_CRITERIA_NOT_MET'
  development_summary: {
    sample_count: number
    input_feature_count: number
    selected_feature_count: number
    roc_auc: number
    roc_auc_lower: number
    roc_auc_upper: number
    pr_auc: number
    permutation_p_value: number | null
  }
  prediction_summary: {
    decision_threshold: number
    predicted_positive_count: number
    predicted_negative_count: number
    positive_class: string
    negative_class: string
  } | null
  protocol: {
    status: string
    frozen_at: string
    intended_use: string
    development_cohort: Record<string, unknown>
    external_cohort: Record<string, unknown>
    endpoint: { name: string; positive_class: string; negative_class: string }
    evaluation: {
      primary_metric: string
      bootstrap_iterations: number
      success_criteria: {
        minimum_point_estimate: number
        minimum_lower_confidence_bound: number
      }
    }
    prohibited_actions: string[]
  }
  result: {
    sample_count: number
    class_counts: { negative: number; positive: number }
    metrics: {
      roc_auc: number
      pr_auc: number
      prevalence: number
      balanced_accuracy: number
      sensitivity: number
      specificity: number
      brier_score: number
      calibration_intercept: number
      calibration_slope: number
    }
    confidence_intervals: {
      method: string
      iterations: number
      metrics: Record<string, { lower: number; upper: number }>
    }
    success: {
      minimum_point_estimate: number
      minimum_lower_confidence_bound: number
      point_estimate_passed: boolean
      lower_bound_passed: boolean
      passed: boolean
    }
    warnings: string[]
    provenance: Record<string, string>
  }
  artifacts: ClassifierExternalValidationArtifact[]
  created_at: string
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

export function fetchProjectClassifierExternalValidations(
  projectId: string,
  signal?: AbortSignal,
): Promise<ClassifierExternalValidation[]> {
  return request(`/projects/${projectId}/classifier-external-validations`, { signal })
}

export function fetchClassifierExternalValidation(
  validationId: string,
  signal?: AbortSignal,
): Promise<ClassifierExternalValidation> {
  return request(`/classifier-external-validations/${validationId}`, { signal })
}

export function classifierExternalValidationArtifactUrl(
  validationId: string,
  artifactName: string,
): string {
  return `${apiBaseUrl}/classifier-external-validations/${encodeURIComponent(validationId)}/artifacts/${encodeURIComponent(artifactName)}`
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
  payload: CreateDimensionReductionRequest & Partial<GuidedAnalysisContext>,
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
  payload: CreateDifferentialExpressionRequest & Partial<GuidedAnalysisContext>,
): Promise<Analysis> {
  return request(`/prepared-datasets/${preparedDatasetId}/analyses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchClassifierDesignOptions(
  preparedDatasetId: string,
  signal?: AbortSignal,
): Promise<DesignOptions> {
  return request(`/prepared-datasets/${preparedDatasetId}/classifier/design-options`, { signal })
}

export function fetchClassifierResults(
  runId: string,
  signal?: AbortSignal,
): Promise<ClassifierResults | MulticlassClassifierResults> {
  return request(`/runs/${runId}/classifier-results`, { signal })
}

export function fetchAnalysisModels(
  analysisId: string,
  signal?: AbortSignal,
): Promise<ModelRecord[]> {
  return request(`/analyses/${analysisId}/models`, { signal })
}

export function fetchModel(modelId: string, signal?: AbortSignal): Promise<ModelRecord> {
  return request(`/models/${modelId}`, { signal })
}

export function fetchModelLockReadiness(
  modelId: string,
  signal?: AbortSignal,
): Promise<ModelLockReadiness> {
  return request(`/models/${modelId}/lock-readiness`, { signal })
}

export function reviewModel(modelId: string, rationale: string): Promise<ModelRecord> {
  return request(`/models/${modelId}/review`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rationale }),
  })
}

export function lockModel(modelId: string, rationale: string): Promise<ModelRecord> {
  return request(`/models/${modelId}/lock`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rationale }),
  })
}

export function cloneModel(modelId: string): Promise<ModelRecord> {
  return request(`/models/${modelId}/clone`, { method: 'POST' })
}

export function retireModel(modelId: string, rationale: string): Promise<ModelRecord> {
  return request(`/models/${modelId}/retire`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rationale }),
  })
}

export function checkModelIntegrity(modelId: string): Promise<ModelIntegrity> {
  return request(`/models/${modelId}/integrity`, { method: 'POST' })
}

export function modelManifestUrl(modelId: string): string {
  return `${apiBaseUrl}/models/${encodeURIComponent(modelId)}/manifest`
}

export function modelPackageUrl(modelId: string): string {
  return `${apiBaseUrl}/models/${encodeURIComponent(modelId)}/package`
}

export function validateClassifierDesign(
  preparedDatasetId: string,
  payload: ClassifierPreviewRequest,
  signal?: AbortSignal,
): Promise<ClassifierDesignValidation> {
  return request(`/prepared-datasets/${preparedDatasetId}/classifier/validate-design`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
}

export function createClassifierAnalysis(
  preparedDatasetId: string,
  payload: ClassifierPreviewRequest & { name: string } & Partial<GuidedAnalysisContext>,
): Promise<Analysis> {
  return request(`/prepared-datasets/${preparedDatasetId}/analyses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...payload, analysis_type: 'classifier' }),
  })
}

export function createSignatureScoringAnalysis(
  preparedDatasetId: string,
  payload: {
    name: string
    method: SignatureScoringMethod
    signatureMappingId: string
    parameters?: Partial<Omit<SignatureScoringParameters, 'signature_mapping_id'>>
    guidedContext?: GuidedAnalysisContext
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
      ...payload.guidedContext,
    }),
  })
}

export function fetchDeconvolutionCapabilities(
  preparedDatasetId: string,
  signal?: AbortSignal,
): Promise<DeconvolutionCapabilities> {
  return request(`/prepared-datasets/${preparedDatasetId}/deconvolution/methods`, { signal })
}

export function fetchDeconvolutionComparison(
  preparedDatasetId: string,
  signal?: AbortSignal,
): Promise<DeconvolutionComparison> {
  return request(`/prepared-datasets/${preparedDatasetId}/deconvolution/comparison`, { signal })
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
    guidedContext?: GuidedAnalysisContext
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
      ...payload.guidedContext,
      random_seed: 0,
    }),
  })
}

export function importCibersortxResult(
  preparedDatasetId: string,
  metadata: CibersortxImportMetadata,
  file: File,
): Promise<Analysis> {
  const form = new FormData()
  form.append('metadata', JSON.stringify(metadata))
  form.append('file', file)
  return request(`/prepared-datasets/${preparedDatasetId}/deconvolution/cibersortx-imports`, {
    method: 'POST',
    body: form,
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

export function fetchAssayProjects(signal?: AbortSignal): Promise<AssayProject[]> {
  return request('/assay-projects', { signal })
}

export function fetchAssayProject(
  assayProjectId: string,
  signal?: AbortSignal,
): Promise<AssayProject> {
  return request(`/assay-projects/${assayProjectId}`, { signal })
}

export function fetchProjectAssayDevelopment(
  projectId: string,
  signal?: AbortSignal,
): Promise<AssayProject | null> {
  return request(`/projects/${projectId}/assay-development`, { signal })
}

export function createAssayProject(payload: {
  project_id: string
  name: string
  proposed_purpose?: string
  specimen_type?: string
  biological_context?: string
  proposed_output?: string
  assay_version?: string
}): Promise<AssayProject> {
  return request('/assay-projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function updateAssayProject(
  assayProjectId: string,
  payload: Partial<Pick<AssayProject, 'name' | 'proposed_purpose' | 'specimen_type' | 'biological_context' | 'proposed_output' | 'assay_version'>>,
): Promise<AssayProject> {
  return request(`/assay-projects/${assayProjectId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchQuestionCatalog(signal?: AbortSignal): Promise<QuestionCatalog> {
  return request('/scientific-questions/catalog', { signal })
}

export function fetchScientificQuestions(
  assayProjectId: string,
  signal?: AbortSignal,
): Promise<ScientificQuestion[]> {
  return request(`/assay-projects/${assayProjectId}/questions`, { signal })
}

export function createScientificQuestion(
  assayProjectId: string,
  payload: { question_key: string; formal_question: string; source?: ScientificQuestion['source'] },
): Promise<ScientificQuestion> {
  return request(`/assay-projects/${assayProjectId}/questions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchAssayReadiness(
  assayProjectId: string,
  signal?: AbortSignal,
): Promise<AssayReadiness> {
  return request(`/assay-projects/${assayProjectId}/readiness`, { signal })
}

export function fetchRecommendations(
  assayProjectId: string,
  signal?: AbortSignal,
): Promise<Recommendation[]> {
  return request(`/assay-projects/${assayProjectId}/recommendations`, { signal })
}

export function resolveRecommendation(
  recommendationId: string,
  resolution: 'accept' | 'reject' | 'modify',
  payload: { rationale: string; modified_action?: Record<string, unknown> },
): Promise<{
  decision: DecisionRecord
  replacement_recommendation: Recommendation | null
  action_launched: false
}> {
  return request(`/recommendations/${recommendationId}/${resolution}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function recordStageDecision(
  assayProjectId: string,
  payload: { requested_stage: AssayLifecycleStage; decision: 'ACCEPT' | 'REJECT' | 'DEFER'; rationale: string },
): Promise<DecisionRecord> {
  return request(`/assay-projects/${assayProjectId}/stage-decisions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchAssayDecisions(
  assayProjectId: string,
  signal?: AbortSignal,
): Promise<DecisionRecord[]> {
  return request(`/assay-projects/${assayProjectId}/decisions`, { signal })
}

export function fetchGuidanceResults(
  assayProjectId: string,
  signal?: AbortSignal,
): Promise<GuidanceResult[]> {
  return request(`/assay-projects/${assayProjectId}/guidance-results`, { signal })
}

export function fetchExperimentInputOptions(
  assayProjectId: string,
  signal?: AbortSignal,
): Promise<ExperimentInputOption[]> {
  return request(`/assay-projects/${assayProjectId}/experiment-input-options`, { signal })
}

export function fetchExperimentDesignOptions(
  preparedDatasetId: string,
  signal?: AbortSignal,
): Promise<ExperimentDesignOptions> {
  return request(`/prepared-datasets/${preparedDatasetId}/experiment-design-options`, { signal })
}

export function createDevelopmentExperiment(
  payload: ExperimentCreatePayload,
): Promise<DevelopmentExperiment> {
  return request('/experiments', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchDevelopmentExperiments(
  assayProjectId: string,
  signal?: AbortSignal,
): Promise<DevelopmentExperiment[]> {
  return request(`/assay-projects/${assayProjectId}/experiments`, { signal })
}

export function fetchDevelopmentExperiment(
  experimentId: string,
  signal?: AbortSignal,
): Promise<DevelopmentExperiment> {
  return request(`/experiments/${experimentId}`, { signal })
}

export function updateDevelopmentExperiment(
  experimentId: string,
  payload: Partial<Pick<ExperimentCreatePayload, 'name' | 'objective' | 'reference_level' | 'reference_condition' | 'comparator_condition' | 'primary_endpoints' | 'secondary_endpoints' | 'declared_questions' | 'reference_level_rationale' | 'condition_contrast_rationale' | 'endpoint_rationale' | 'assignments'>>,
): Promise<DevelopmentExperiment> {
  return request(`/experiments/${experimentId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function lockDevelopmentExperiment(experimentId: string): Promise<DevelopmentExperiment> {
  return request(`/experiments/${experimentId}/lock-execution-revision`, { method: 'POST' })
}

export function runDevelopmentExperiment(
  experimentId: string,
): Promise<{ experiment: DevelopmentExperiment; run_id: string; run_state: 'QUEUED' }> {
  return request(`/experiments/${experimentId}/run`, { method: 'POST' })
}

export function cloneDevelopmentExperiment(experimentId: string): Promise<DevelopmentExperiment> {
  return request(`/experiments/${experimentId}/clone`, { method: 'POST' })
}

export function acceptDevelopmentExperimentFollowUp(
  experimentId: string,
  recommendationId: string,
  rationale: string,
): Promise<DevelopmentExperiment> {
  return request(`/experiments/${experimentId}/recommendations/${recommendationId}/accept-follow-up`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rationale }),
  })
}

export function fetchDevelopmentExperimentResults(
  experimentId: string,
  signal?: AbortSignal,
): Promise<ExperimentResults> {
  return request(`/experiments/${experimentId}/results`, { signal })
}

export function fetchDevelopmentExperimentRecommendations(
  experimentId: string,
  signal?: AbortSignal,
): Promise<Recommendation[]> {
  return request(`/experiments/${experimentId}/recommendations`, { signal })
}

export function experimentWetLabPackageUrl(experimentId: string): string {
  return `${apiBaseUrl}/experiments/${encodeURIComponent(experimentId)}/wet-lab-package`
}

export function fetchStudyInputOptions(
  assayProjectId: string,
  signal?: AbortSignal,
): Promise<StudyInputOptions> {
  return request(`/assay-projects/${assayProjectId}/study-input-options`, { signal })
}

export function fetchAnalyticalStudies(
  assayProjectId: string,
  signal?: AbortSignal,
): Promise<AnalyticalStudy[]> {
  return request(`/assay-projects/${assayProjectId}/studies`, { signal })
}

export function fetchAnalyticalStudy(
  studyId: string,
  signal?: AbortSignal,
): Promise<AnalyticalStudy> {
  return request(`/studies/${studyId}`, { signal })
}

export function createAnalyticalStudy(payload: StudyCreatePayload): Promise<AnalyticalStudy> {
  return request('/studies', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function updateAnalyticalStudy(
  studyId: string,
  payload: Partial<Pick<StudyCreatePayload, 'name' | 'objective' | 'assignments' | 'factors' | 'criteria' | 'confidence_level' | 'bootstrap_iterations' | 'threshold_proximity_band' | 'reference_level' | 'level_rationale' | 'reference_condition' | 'comparator_condition' | 'equivalence_margin' | 'condition_rationale'>>,
): Promise<AnalyticalStudy> {
  return request(`/studies/${studyId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function lockAnalyticalStudy(studyId: string): Promise<AnalyticalStudy> {
  return request(`/studies/${studyId}/lock`, { method: 'POST' })
}

export function runAnalyticalStudy(
  studyId: string,
): Promise<{ study: AnalyticalStudy; run_id: string; run_state: 'QUEUED' }> {
  return request(`/studies/${studyId}/run`, { method: 'POST' })
}

export function cloneAnalyticalStudy(studyId: string): Promise<AnalyticalStudy> {
  return request(`/studies/${studyId}/clone`, { method: 'POST' })
}

export function fetchAnalyticalStudyResults(
  studyId: string,
  signal?: AbortSignal,
): Promise<StudyResults> {
  return request(`/studies/${studyId}/results`, { signal })
}
