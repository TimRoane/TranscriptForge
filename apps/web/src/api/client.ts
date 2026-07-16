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

export interface QCSummary {
  status: 'PASS' | 'REVIEW' | 'SEVERE_REVIEW'
  samples: QCSample[]
  flags: Array<{ sample_id: string; status: 'PASS' | 'REVIEW'; reasons: string[] }>
}

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

export interface Analysis {
  id: string
  project_id: string
  prepared_dataset_id: string
  analysis_type: 'dimension_reduction' | 'differential_expression'
  name: string
  description: string | null
  configuration_json: DimensionReductionConfiguration | DifferentialExpressionConfiguration
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
  role: 'count_matrix' | 'expression_matrix' | 'sample_metadata',
  file: File,
): Promise<DatasetFile> {
  const form = new FormData()
  form.append('role', role)
  form.append('file', file)
  return request(`/datasets/${datasetId}/files`, { method: 'POST', body: form })
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
