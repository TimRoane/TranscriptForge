import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

const health = { status: 'ok', service: 'transcriptforge-api', version: '0.1.0', environment: 'test' }
const project = {
  id: 'project-1',
  name: 'Airway study',
  description: 'Dexamethasone experiment',
  owner_id: 'local-user',
  created_at: '2026-07-16T00:00:00Z',
  updated_at: '2026-07-16T00:00:00Z',
}
const dataset = {
  id: 'dataset-1',
  project_id: 'project-1',
  name: 'Airway counts',
  description: null,
  modality: 'bulk_rnaseq',
  source_kind: 'count_matrix',
  organism: 'Homo sapiens',
  genome_build: 'GRCh38',
  annotation_release: 'GENCODE 49',
  status: 'valid',
  created_at: '2026-07-16T00:00:00Z',
  updated_at: '2026-07-16T00:00:00Z',
}
const completedRun = {
  id: 'run-1',
  run_type: 'dataset_validation',
  dataset_id: 'dataset-1',
  prepared_dataset_id: null,
  state: 'SUCCEEDED',
  profile: 'test',
  nextflow_session_id: 'session-1',
  nextflow_run_name: 'tf_run_1',
  exit_code: 0,
  error_summary: null,
  started_at: '2026-07-16T00:00:01Z',
  finished_at: '2026-07-16T00:00:02Z',
  created_at: '2026-07-16T00:00:00Z',
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } })
}

function renderApp(path = '/') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter
        initialEntries={[path]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('App', () => {
  afterEach(() => vi.restoreAllMocks())

  it('renders the research-use dashboard and existing projects', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/projects')) return jsonResponse([project])
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp()

    expect(screen.getByText('Research use only')).toBeInTheDocument()
    expect(await screen.findByText('Airway study')).toBeInTheDocument()
    expect(await screen.findByLabelText('API connected')).toBeInTheDocument()
  })

  it('creates a project and navigates to its dataset page', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/projects') && init?.method === 'POST') return jsonResponse(project, 201)
      if (url.endsWith('/projects')) return jsonResponse([])
      if (url.endsWith('/projects/project-1')) return jsonResponse(project)
      if (url.endsWith('/projects/project-1/datasets')) return jsonResponse([])
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp()
    fireEvent.click(await screen.findByRole('button', { name: 'New project' }))
    fireEvent.change(screen.getByRole('textbox', { name: /Project name/ }), {
      target: { value: 'Airway study' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(screen.getByText('Datasets')).toBeInTheDocument())
    expect(screen.getByText('No datasets registered yet.')).toBeInTheDocument()
  })

  it('renders completed validation state and matrix preview on the project dashboard', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/projects/project-1')) return jsonResponse(project)
      if (url.endsWith('/projects/project-1/datasets')) return jsonResponse([dataset])
      if (url.endsWith('/datasets/dataset-1/validation-runs')) return jsonResponse([completedRun])
      if (url.endsWith('/datasets/dataset-1/preparation-runs')) return jsonResponse([])
      if (url.endsWith('/datasets/dataset-1/prepared-versions')) return jsonResponse([])
      if (url.endsWith('/runs/run-1')) return jsonResponse(completedRun)
      if (url.endsWith('/runs/run-1/artifacts')) return jsonResponse([])
      if (url.endsWith('/runs/run-1/validation-report')) {
        return jsonResponse({
          schema_version: '1.0.0',
          status: 'VALID',
          matrix: { orientation: 'features_by_samples', sample_count: 1, feature_count: 1 },
          metadata: { sample_count: 1, column_count: 2 },
          findings: [],
          suppressed_findings: {},
          preview: {
            matrix_columns: ['sample_1'],
            matrix_rows: [{ id: 'ENSG000001', values: { sample_1: '42' } }],
            metadata_rows: [{ sample_id: 'sample_1', condition: 'control' }],
          },
        })
      }
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp('/projects/project-1')

    expect(await screen.findByText('Airway counts')).toBeInTheDocument()
    expect(await screen.findByText(/VALID: 1 features and 1 samples/)).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Matrix orientation preview' })).toBeInTheDocument()
    expect(screen.getByText('ENSG000001')).toBeInTheDocument()
  })

  it('renders prepared dataset QC and mapping provenance', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/prepared-datasets/prepared-1')) {
        return jsonResponse({
          id: 'prepared-1',
          dataset_id: 'dataset-1',
          version: 1,
          preparation_run_id: 'preparation-run-1',
          value_types_available: ['raw_counts', 'log_expression'],
          sample_count: 1,
          feature_count: 5,
          qc_status: 'PASS',
          created_at: '2026-07-16T00:00:00Z',
        })
      }
      if (url.endsWith('/datasets/dataset-1')) return jsonResponse(dataset)
      if (url.endsWith('/runs/preparation-run-1/qc-summary')) {
        return jsonResponse({
          status: 'PASS',
          samples: [{
            sample_id: 'sample_1',
            library_size: 42,
            detected_features: 1,
            detected_fraction: 0.2,
            zero_fraction: 0.8,
          }],
          flags: [{ sample_id: 'sample_1', status: 'PASS', reasons: [] }],
        })
      }
      if (url.endsWith('/runs/preparation-run-1/feature-mapping-summary')) {
        return jsonResponse({
          prepared_dataset_id: 'prepared-1',
          prepared_version: 1,
          sample_count: 1,
          feature_count: 5,
          value_types_available: ['raw_counts', 'log_expression'],
          qc_status: 'PASS',
          mapped_feature_count: 5,
          unmapped_feature_count: 0,
          duplicate_group_count: 0,
          mapping_coverage: 1,
        })
      }
      if (url.endsWith('/runs/preparation-run-1/artifacts')) return jsonResponse([])
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp('/prepared-datasets/prepared-1')

    expect(await screen.findByRole('heading', { name: 'Expression Bundle' })).toBeInTheDocument()
    expect(await screen.findByText('100.0%')).toBeInTheDocument()
    expect(await screen.findByText('sample_1')).toBeInTheDocument()
    expect(screen.getByText(/42 total · 1 detected/)).toBeInTheDocument()
    expect(screen.getByText('5 mapped')).toBeInTheDocument()
  })

  it('selects UMAP controls and launches the frozen method configuration', async () => {
    const prepared = {
      id: 'prepared-1',
      dataset_id: 'dataset-1',
      version: 1,
      preparation_run_id: 'preparation-run-1',
      value_types_available: ['raw_counts', 'log_expression'],
      sample_count: 72,
      feature_count: 2000,
      qc_status: 'PASS',
      created_at: '2026-07-16T00:00:00Z',
    }
    const analysis = {
      id: 'analysis-umap',
      project_id: 'project-1',
      prepared_dataset_id: 'prepared-1',
      analysis_type: 'dimension_reduction',
      name: 'UMAP embedding',
      description: null,
      configuration_json: {
        analysis_type: 'dimension_reduction',
        method: 'umap',
        assay: 'log_expression',
        parameters: {},
        random_seed: 20260716,
      },
      created_at: '2026-07-16T00:00:00Z',
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/prepared-datasets/prepared-1/analyses') && init?.method === 'POST') {
        return jsonResponse(analysis, 201)
      }
      if (url.endsWith('/analyses/analysis-umap/run') && init?.method === 'POST') {
        return jsonResponse({ ...completedRun, id: 'analysis-run-1', run_type: 'analysis' }, 202)
      }
      if (url.endsWith('/prepared-datasets/prepared-1')) return jsonResponse(prepared)
      if (url.endsWith('/datasets/dataset-1')) return jsonResponse(dataset)
      if (url.endsWith('/runs/preparation-run-1/qc-summary')) {
        return jsonResponse({ status: 'PASS', samples: [], flags: [] })
      }
      if (url.endsWith('/runs/preparation-run-1/feature-mapping-summary')) {
        return jsonResponse({
          prepared_dataset_id: 'prepared-1', prepared_version: 1, sample_count: 72,
          feature_count: 2000, value_types_available: ['log_expression'], qc_status: 'PASS',
          mapped_feature_count: 2000, unmapped_feature_count: 0, duplicate_group_count: 0,
          mapping_coverage: 1,
        })
      }
      if (url.endsWith('/runs/preparation-run-1/artifacts')) return jsonResponse([])
      if (url.endsWith('/prepared-datasets/prepared-1/analyses')) return jsonResponse([])
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp('/prepared-datasets/prepared-1')
    const methodSelectors = await screen.findAllByRole('combobox', { name: 'Method' })
    fireEvent.mouseDown(methodSelectors.find((element) => element.textContent === 'PCA')!)
    fireEvent.click(await screen.findByRole('option', { name: 'UMAP' }))

    expect(screen.getByRole('spinbutton', { name: 'Neighbors' })).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: 'Min. distance' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Run analysis' }))

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => String(input).endsWith('/prepared-datasets/prepared-1/analyses')
          && init?.method === 'POST',
      )
      expect(createCall).toBeDefined()
      expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
        method: 'umap',
        parameters: { neighbors: 15, min_distance: 0.2, top_variable_features: 500 },
        random_seed: 20260716,
      })
    })
  })

  it('renders hierarchical clustering dendrogram and heatmap results', async () => {
    const analysis = {
      id: 'analysis-clustering',
      project_id: 'project-1',
      prepared_dataset_id: 'prepared-1',
      analysis_type: 'dimension_reduction',
      name: 'Hierarchical sample clustering',
      description: null,
      configuration_json: {
        analysis_type: 'dimension_reduction',
        method: 'hierarchical_clustering',
        assay: 'log_expression',
        parameters: {},
        random_seed: 20260716,
      },
      created_at: '2026-07-16T00:00:00Z',
    }
    const analysisRun = {
      ...completedRun,
      id: 'analysis-run-1',
      run_type: 'analysis',
      analysis_id: 'analysis-clustering',
      dataset_id: null,
      prepared_dataset_id: 'prepared-1',
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/analyses/analysis-clustering')) return jsonResponse(analysis)
      if (url.endsWith('/analyses/analysis-clustering/runs')) return jsonResponse([analysisRun])
      if (url.endsWith('/prepared-datasets/prepared-1')) {
        return jsonResponse({
          id: 'prepared-1', dataset_id: 'dataset-1', version: 1,
          preparation_run_id: 'preparation-run-1', value_types_available: ['log_expression'],
          sample_count: 2, feature_count: 20, qc_status: 'PASS',
          created_at: '2026-07-16T00:00:00Z',
        })
      }
      if (url.endsWith('/runs/analysis-run-1/dendrogram-plot')) {
        return jsonResponse({
          schema_version: '1.0.0', analysis_id: 'analysis-clustering',
          sample_order: ['sample_A', 'sample_B'], icoord: [[5, 5, 15, 15]],
          dcoord: [[0, 1, 1, 0]], color_list: ['C0'],
          clusters: { sample_A: 1, sample_B: 2 }, metadata: {},
        })
      }
      if (url.endsWith('/runs/analysis-run-1/correlation-heatmap')) {
        return jsonResponse({
          schema_version: '1.0.0', sample_order: ['sample_A', 'sample_B'],
          values: [[1, 0.2], [0.2, 1]], metadata: {},
        })
      }
      if (url.endsWith('/runs/analysis-run-1/result-manifest')) {
        return jsonResponse({
          schema_version: '1.0.0', analysis_type: 'dimension_reduction',
          title: 'Hierarchical sample clustering',
          summary_metrics: [{ label: 'Samples', value: 2 }], warnings: [],
        })
      }
      if (url.endsWith('/runs/analysis-run-1/artifacts')) return jsonResponse([])
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp('/analyses/analysis-clustering')

    expect(await screen.findByRole('img', { name: 'Hierarchical sample dendrogram' })).toBeInTheDocument()
    expect(await screen.findByRole('img', { name: 'Sample correlation heatmap' })).toBeInTheDocument()
    expect(screen.getByText('Cluster 1: 1 samples')).toBeInTheDocument()
  })

  it('previews and saves an edgeR QL differential-expression design', async () => {
    const prepared = {
      id: 'prepared-1', dataset_id: 'dataset-1', version: 1,
      preparation_run_id: 'preparation-run-1', value_types_available: ['raw_counts', 'log_expression'],
      sample_count: 8, feature_count: 2000, qc_status: 'PASS',
      created_at: '2026-07-16T00:00:00Z',
    }
    const validation = {
      valid: true,
      formula: '~ treatment',
      resolved_method: 'deseq2',
      contrast_label: 'stimulated versus vehicle within treatment',
      sample_count: 8,
      contrast_counts: { stimulated: 4, vehicle: 4 },
      design_matrix_columns: ['Intercept', 'treatment[stimulated]'],
      design_matrix_rank: 2,
      design_cells: [],
      errors: [],
      warnings: [],
    }
    const saved = {
      id: 'analysis-de', project_id: 'project-1', prepared_dataset_id: 'prepared-1',
      analysis_type: 'differential_expression', name: 'stimulated versus vehicle', description: null,
      configuration_json: {
        analysis_type: 'differential_expression', method: 'deseq2', assay: 'raw_counts',
        parameters: {
          design: {
            primary_variable: 'treatment', covariates: ['batch'], block_column: null,
            interaction_terms: [], reference_levels: { treatment: 'vehicle' },
          },
          contrast: { variable: 'treatment', numerator: 'stimulated', denominator: 'vehicle' },
          low_count_threshold: 10, minimum_samples: 2, fdr_threshold: 0.05,
          absolute_log2_fold_change: 1, independent_filtering: true, shrinkage: true,
        },
        random_seed: 20260716, design_formula: validation.formula,
        contrast_label: validation.contrast_label, design_validation: validation,
      },
      created_at: '2026-07-16T00:00:00Z',
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/prepared-datasets/prepared-1/differential-expression/design-options')) {
        return jsonResponse({
          sample_count: 8, assays: ['raw_counts', 'log_expression'],
          variables: [
            { name: 'treatment', kind: 'categorical', levels: ['vehicle', 'stimulated'], missing_count: 0, unique_count: 2 },
            { name: 'batch', kind: 'categorical', levels: ['batch_1', 'batch_2'], missing_count: 0, unique_count: 2 },
          ],
        })
      }
      if (url.endsWith('/prepared-datasets/prepared-1/differential-expression/validate-design')) {
        const request = JSON.parse(String(init?.body)) as { method?: string }
        return jsonResponse({
          ...validation,
          resolved_method: request.method === 'edger_ql' ? 'edger_ql' : 'deseq2',
        })
      }
      if (url.endsWith('/prepared-datasets/prepared-1/analyses') && init?.method === 'POST') {
        return jsonResponse(saved, 201)
      }
      if (url.endsWith('/prepared-datasets/prepared-1')) return jsonResponse(prepared)
      if (url.endsWith('/datasets/dataset-1')) return jsonResponse(dataset)
      if (url.endsWith('/runs/preparation-run-1/qc-summary')) {
        return jsonResponse({ status: 'PASS', samples: [], flags: [] })
      }
      if (url.endsWith('/runs/preparation-run-1/feature-mapping-summary')) {
        return jsonResponse({
          prepared_dataset_id: 'prepared-1', prepared_version: 1, sample_count: 8,
          feature_count: 2000, value_types_available: ['raw_counts', 'log_expression'],
          qc_status: 'PASS', mapped_feature_count: 2000, unmapped_feature_count: 0,
          duplicate_group_count: 0, mapping_coverage: 1,
        })
      }
      if (url.endsWith('/runs/preparation-run-1/artifacts')) return jsonResponse([])
      if (url.endsWith('/prepared-datasets/prepared-1/analyses')) return jsonResponse([])
      if (url.endsWith('/analyses/analysis-de')) return jsonResponse(saved)
      if (url.endsWith('/analyses/analysis-de/runs')) return jsonResponse([])
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp('/prepared-datasets/prepared-1')

    expect(await screen.findByText('~ treatment')).toBeInTheDocument()
    expect(screen.getByText('Method: deseq2')).toBeInTheDocument()
    expect(screen.getByText('stimulated: 4 samples')).toBeInTheDocument()
    fireEvent.mouseDown(screen.getAllByRole('combobox', { name: 'Method' })[0])
    fireEvent.click(screen.getByRole('option', { name: 'edgeR QL' }))
    expect(await screen.findByText('Method: edger_ql')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save validated design' }))

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => String(input).endsWith('/prepared-datasets/prepared-1/analyses')
          && init?.method === 'POST',
      )
      expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
        analysis_type: 'differential_expression',
        assay: 'raw_counts',
        method: 'edger_ql',
        parameters: {
          design: { primary_variable: 'treatment', covariates: [] },
          contrast: { numerator: 'stimulated', denominator: 'vehicle' },
        },
      })
    })
  })

  it('renders completed limma results with method-specific abundance semantics', async () => {
    let savedSignatureRequest: Record<string, unknown> | null = null
    const validation = {
      valid: true, formula: '~ subject_id + treatment', resolved_method: 'limma',
      contrast_label: 'stimulated versus vehicle within treatment', sample_count: 4,
      contrast_counts: { stimulated: 2, vehicle: 2 },
      design_matrix_columns: ['Intercept', 'subject_id[donor_2]', 'treatment[stimulated]'],
      design_matrix_rank: 3, design_cells: [], errors: [], warnings: [],
    }
    const analysis = {
      id: 'analysis-limma', project_id: 'project-1', prepared_dataset_id: 'prepared-1',
      analysis_type: 'differential_expression', name: 'Paired limma response', description: null,
      configuration_json: {
        analysis_type: 'differential_expression', method: 'limma', assay: 'log_expression',
        parameters: {
          design: {
            primary_variable: 'treatment', covariates: [], block_column: 'subject_id',
            interaction_terms: [], reference_levels: { treatment: 'vehicle' },
          },
          contrast: { variable: 'treatment', numerator: 'stimulated', denominator: 'vehicle' },
          low_count_threshold: 10, minimum_samples: 2, fdr_threshold: 0.05,
          absolute_log2_fold_change: 1, independent_filtering: true, shrinkage: true,
        },
        random_seed: 20260716, design_formula: validation.formula,
        contrast_label: validation.contrast_label, design_validation: validation,
      },
      created_at: '2026-07-16T00:00:00Z',
    }
    const analysisRun = {
      ...completedRun, id: 'limma-run-1', run_type: 'analysis', analysis_id: 'analysis-limma',
      prepared_dataset_id: 'prepared-1', dataset_id: 'dataset-1',
    }
    const plot = {
      schema_version: '1.0.0', analysis_id: 'analysis-limma',
      x_label: 'log2 fold change', y_label: '-log10 p-value',
      points: [
        { feature_id: 'gene_up', x: 1.4, y: 8.2, adjusted_p_value: 0.0001, significant: true },
        { feature_id: 'gene_null', x: 0.1, y: 0.4, adjusted_p_value: 0.8, significant: false },
      ],
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/analyses/analysis-limma')) return jsonResponse(analysis)
      if (url.endsWith('/analyses/analysis-limma/runs')) return jsonResponse([analysisRun])
      if (url.endsWith('/prepared-datasets/prepared-1')) {
        return jsonResponse({
          id: 'prepared-1', dataset_id: 'dataset-1', version: 1,
          preparation_run_id: 'preparation-run-1', value_types_available: ['log_expression'],
          sample_count: 4, feature_count: 2, qc_status: 'PASS',
          created_at: '2026-07-16T00:00:00Z',
        })
      }
      if (url.endsWith('/runs/limma-run-1/volcano-plot')) return jsonResponse(plot)
      if (url.endsWith('/runs/limma-run-1/ma-plot')) {
        return jsonResponse({ ...plot, x_label: 'average log2 expression' })
      }
      if (url.endsWith('/runs/limma-run-1/p-value-distribution')) {
        return jsonResponse({
          schema_version: '1.0.0', analysis_id: 'analysis-limma', bin_width: 0.05,
          finite_p_value_count: 2, missing_p_value_count: 0,
          bins: [{ start: 0, end: 0.05, count: 1 }, { start: 0.05, end: 0.1, count: 1 }],
        })
      }
      if (url.endsWith('/runs/limma-run-1/expression-heatmap')) {
        return jsonResponse({
          schema_version: '1.0.0', analysis_id: 'analysis-limma', assay: 'log_expression',
          scale: 'feature_z_score', source: 'input log-expression assay',
          sample_ordering: 'subject_id then treatment',
          feature_ids: ['gene_up', 'gene_null'],
          sample_ids: ['sample_A', 'sample_B'], values: [[-1, 1], [0.2, -0.2]],
          metadata: {
            sample_A: { treatment: 'vehicle' }, sample_B: { treatment: 'stimulated' },
          },
          feature_annotations: {
            gene_up: { log2_fold_change: 1.4, adjusted_p_value: 0.0001, significant: true },
            gene_null: { log2_fold_change: 0.1, adjusted_p_value: 0.8, significant: false },
          },
          contrast: { variable: 'treatment', numerator: 'stimulated', denominator: 'vehicle' },
        })
      }
      if (url.includes('/runs/limma-run-1/differential-expression/results?')) {
        return jsonResponse({
          items: [
            {
              feature_id: 'gene_up', gene_symbol: 'UP1', base_expression: 8.2,
              log2_fold_change: 1.4, standard_error: 0.2, statistic: 7,
              p_value: 1e-8, adjusted_p_value: 0.0001, significant: true,
              contrast: 'stimulated versus vehicle within treatment', method: 'limma',
            },
            {
              feature_id: 'gene_null', gene_symbol: null, base_expression: 6.1,
              log2_fold_change: 0.1, standard_error: 0.3, statistic: 0.33,
              p_value: 0.4, adjusted_p_value: 0.8, significant: false,
              contrast: 'stimulated versus vehicle within treatment', method: 'limma',
            },
          ],
          total: 2, offset: 0, limit: 25, base_expression_label: 'Average log2 expression',
        })
      }
      if (url.endsWith('/runs/limma-run-1/differential-expression/features/gene_up')) {
        return jsonResponse({
          result: {
            feature_id: 'gene_up', gene_symbol: 'UP1', base_expression: 8.2,
            log2_fold_change: 1.4, standard_error: 0.2, statistic: 7,
            p_value: 1e-8, adjusted_p_value: 0.0001, significant: true,
            contrast: 'stimulated versus vehicle within treatment', method: 'limma',
          },
          base_expression_label: 'Average log2 expression',
          expression_profile: {
            assay: 'log_expression', source: 'input log-expression assay',
            value_label: 'input log-expression assay',
            contrast: { variable: 'treatment', numerator: 'stimulated', denominator: 'vehicle' },
            values: [
              { sample_id: 'sample_A', value: 7.5, metadata: { treatment: 'vehicle' } },
              { sample_id: 'sample_B', value: 9.0, metadata: { treatment: 'stimulated' } },
            ],
            group_summaries: [
              { level: 'vehicle', sample_count: 1, mean: 7.5, median: 7.5, minimum: 7.5, maximum: 7.5 },
              { level: 'stimulated', sample_count: 1, mean: 9, median: 9, minimum: 9, maximum: 9 },
            ],
          },
        })
      }
      if (url.endsWith('/runs/limma-run-1/signatures') && init?.method === 'POST') {
        savedSignatureRequest = JSON.parse(String(init.body)) as Record<string, unknown>
        return jsonResponse({
          id: 'signature-1', project_id: 'project-1', prepared_dataset_id: 'prepared-1',
          source_analysis_id: 'analysis-limma', source_run_id: 'limma-run-1',
          name: 'Reviewed treatment genes', description: null, status: 'draft',
          feature_ids: ['gene_up'], feature_snapshot_json: [],
          selection_json: { source_result_sha256: 'a'.repeat(64) },
          created_at: '2026-07-16T00:00:00Z', updated_at: '2026-07-16T00:00:00Z',
          research_use_warning: 'Not independently validated.',
        }, 201)
      }
      if (url.endsWith('/runs/limma-run-1/signatures')) return jsonResponse([])
      if (url.endsWith('/runs/limma-run-1/result-manifest')) {
        return jsonResponse({
          schema_version: '1.0.0', analysis_type: 'differential_expression',
          title: 'limma: stimulated versus vehicle',
          summary_metrics: [{ label: 'Significant features', value: 1 }],
          warnings: ['Count filtering is not applied to limma log-expression fits.'],
        })
      }
      if (url.endsWith('/runs/limma-run-1/artifacts')) return jsonResponse([])
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp('/analyses/analysis-limma')

    expect(await screen.findByRole('img', { name: 'Volcano plot' })).toBeInTheDocument()
    expect(await screen.findByRole('img', { name: 'MA plot' })).toBeInTheDocument()
    expect(await screen.findByRole('img', { name: 'P-value distribution' })).toBeInTheDocument()
    expect(await screen.findByRole('img', { name: 'Top-feature expression heatmap' })).toBeInTheDocument()
    expect(await screen.findByRole('table', { name: 'Differential-expression results' })).toBeInTheDocument()
    expect(screen.getByText('UP1')).toBeInTheDocument()
    expect(screen.getByText('average log2 expression')).toBeInTheDocument()
    expect(screen.getByText(/row z-scores/)).toBeInTheDocument()
    expect(screen.getByText(/Count filtering is not applied/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run again' })).toBeEnabled()

    fireEvent.click(screen.getByRole('checkbox', { name: 'Select gene_up for signature' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save 1 selected as signature' }))
    expect(screen.getByText(/candidate generation, not independent validation/)).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Signature name' }), {
      target: { value: 'Reviewed treatment genes' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save signature draft' }))
    expect(await screen.findByText(/Saved “Reviewed treatment genes”/)).toBeInTheDocument()
    await waitFor(() =>
      expect(
        screen.queryByRole('dialog', { name: 'Save candidate gene signature' }),
      ).not.toBeInTheDocument(),
    )
    expect(savedSignatureRequest).toMatchObject({
      name: 'Reviewed treatment genes', feature_ids: ['gene_up'],
    })

    fireEvent.change(screen.getByRole('textbox', { name: 'Search gene symbol or ID' }), {
      target: { value: 'gene_up' },
    })
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => (
      String(input).includes('search=gene_up')
    ))).toBe(true))
    fireEvent.click(await screen.findByText('log2 FC'))
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => (
      String(input).includes('sort_by=log2_fold_change')
    ))).toBe(true))

    fireEvent.click(screen.getAllByLabelText('Open gene_up details')[0])
    expect(await screen.findByRole('dialog', { name: 'Gene detail' })).toBeInTheDocument()
    expect(await screen.findByRole('img', { name: 'Per-gene expression plot' })).toBeInTheDocument()
    expect(screen.getAllByText('stimulated versus vehicle within treatment').length).toBeGreaterThan(0)
  })
})
