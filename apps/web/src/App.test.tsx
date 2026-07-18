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
const externalValidation = {
  id: 'validation-1',
  project_id: 'project-1',
  name: 'GSE140494 to GSE32646 pCR validation',
  description: 'Prespecified external validation',
  development_accession: 'GSE140494',
  external_accession: 'GSE32646',
  protocol_id: 'breast-pcr-gse140494-to-gse32646-v1',
  status: 'SUCCESS_CRITERIA_NOT_MET',
  development_summary: {
    sample_count: 91, input_feature_count: 23963, selected_feature_count: 500,
    roc_auc: 0.6234271099744245, roc_auc_lower: 0.5116223363774735,
    roc_auc_upper: 0.7780881459058941, pr_auc: 0.3360480525435074,
    permutation_p_value: 0.0297029702970297,
  },
  prediction_summary: {
    decision_threshold: 0.2528821468, predicted_positive_count: 74,
    predicted_negative_count: 41, positive_class: 'pCR', negative_class: 'nCR',
  },
  protocol: {
    status: 'prospectively_frozen', frozen_at: '2026-07-17T22:00:00Z',
    intended_use: 'Research-only prediction of pathological complete response.',
    development_cohort: {}, external_cohort: {},
    endpoint: {
      name: 'Pathological complete response', positive_class: 'pCR', negative_class: 'nCR',
    },
    evaluation: {
      primary_metric: 'roc_auc', bootstrap_iterations: 2000,
      success_criteria: { minimum_point_estimate: 0.65, minimum_lower_confidence_bound: 0.5 },
    },
    prohibited_actions: ['Do not tune on GSE32646'],
  },
  result: {
    sample_count: 115, class_counts: { negative: 88, positive: 27 },
    metrics: {
      roc_auc: 0.6191077441, pr_auc: 0.3120156105, prevalence: 0.2347826087,
      balanced_accuracy: 0.5877525253, sensitivity: 0.7777777778,
      specificity: 0.3977272727, brier_score: 0.1776467652,
      calibration_intercept: -0.3344043293, calibration_slope: 0.9267055601,
    },
    confidence_intervals: {
      method: 'stratified_experimental_unit_percentile_bootstrap', iterations: 2000,
      metrics: {
        roc_auc: { lower: 0.5029250842, upper: 0.7256207912 },
      },
    },
    success: {
      minimum_point_estimate: 0.65, minimum_lower_confidence_bound: 0.5,
      point_estimate_passed: false, lower_bound_passed: true, passed: false,
    },
    warnings: ['Research only'], provenance: { protocol_sha256: 'a'.repeat(64) },
  },
  artifacts: [{
    name: 'result', title: 'External validation result',
    filename: 'result.json', mime_type: 'application/json', size_bytes: 100,
    sha256: 'b'.repeat(64),
  }],
  created_at: '2026-07-18T00:00:00Z',
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
const deconvolutionCapabilities = {
  prepared_dataset_id: 'prepared-1',
  registry_version: '2026.07.0',
  registry_sha256: 'f'.repeat(64),
  methods: [{
    method: {
      id: 'epic', display_name: 'EPIC', execution_mode: 'native',
      implementation_status: 'license_blocked', result_type: 'cell_fraction',
      quantity_label: 'Estimated cell fraction', unit: 'fraction',
      composition_constraint: 'bounded_sum', within_sample_cell_type_comparison: true,
      between_sample_comparison: true,
      input: {
        organism: 'Homo sapiens', feature_level: 'gene', identifier_namespace: 'gene_symbol',
        assay_options: [{
          name: 'tpm', scales: ['linear'], value_types: ['nonnegative_continuous'],
        }],
        minimum_reference_overlap: 0.5, negative_values_permitted: false,
      },
      references: [{ id: 'TRef', label: 'Tumor-infiltrating cell reference' }],
      default_reference: 'TRef',
      interpretation: 'Fractions are method- and reference-specific estimates.',
      source_url: 'https://epic.unil.ch/',
    },
    compatible_assays: ['tpm'], configuration_available: true,
    execution_available: false, blocked_reasons: ['Upstream license acceptance is required.'],
  }, {
    method: {
      id: 'quantiseq', display_name: 'quanTIseq', execution_mode: 'native',
      implementation_status: 'available', result_type: 'cell_fraction',
      quantity_label: 'Estimated immune-cell fraction', unit: 'fraction',
      composition_constraint: 'sum_to_one_with_other', within_sample_cell_type_comparison: true,
      between_sample_comparison: true,
      input: {
        organism: 'Homo sapiens', feature_level: 'gene', identifier_namespace: 'gene_symbol',
        assay_options: [{
          name: 'tpm', scales: ['linear'], value_types: ['nonnegative_continuous'],
        }],
        minimum_reference_overlap: 0.5, negative_values_permitted: false,
      },
      references: [{ id: 'TIL10', label: 'quanTIseq TIL10 immune reference' }],
      default_reference: 'TIL10',
      interpretation: 'Outputs are immune-cell fractions plus an uncharacterized Other fraction.',
      source_url: 'https://icbi.i-med.ac.at/quantiseq/',
    },
    compatible_assays: ['tpm'], configuration_available: true,
    execution_available: true, blocked_reasons: [],
  }, {
    method: {
      id: 'cibersortx_external', display_name: 'CIBERSORTx result import',
      execution_mode: 'external_import', implementation_status: 'available',
      result_type: 'cell_fraction', quantity_label: 'Externally estimated relative fraction',
      unit: 'fraction', composition_constraint: 'declared_by_import',
      within_sample_cell_type_comparison: true, between_sample_comparison: true,
      input: {
        organism: 'Homo sapiens', feature_level: 'gene', identifier_namespace: 'gene_symbol',
        assay_options: [{
          name: 'tpm', scales: ['linear'], value_types: ['nonnegative_continuous'],
        }],
        minimum_reference_overlap: 0, negative_values_permitted: false,
      },
      references: [], default_reference: null,
      interpretation: 'Externally estimated relative fractions with frozen provenance.',
      source_url: 'https://cibersortx.stanford.edu/',
    },
    compatible_assays: ['tpm'], configuration_available: true,
    execution_available: false, blocked_reasons: ['External import only.'],
  }],
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
    expect(screen.getByRole('heading', { name: 'From expression data to auditable results.' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open workspace' })).toHaveAttribute('href', '/projects')
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

    renderApp('/projects')
    fireEvent.click(await screen.findByRole('button', { name: 'New project' }))
    fireEvent.change(screen.getByRole('textbox', { name: /Project name/ }), {
      target: { value: 'Airway study' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(screen.getByText('Datasets')).toBeInTheDocument())
    expect(screen.getByText('No datasets registered yet.')).toBeInTheDocument()
  })

  it('opens a frozen external classifier validation dashboard from its project', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/projects/project-1')) return jsonResponse(project)
      if (url.endsWith('/projects/project-1/datasets')) return jsonResponse([])
      if (url.endsWith('/projects/project-1/signature-definitions')) return jsonResponse([])
      if (url.endsWith('/projects/project-1/classifier-external-validations')) {
        return jsonResponse([externalValidation])
      }
      if (url.endsWith('/classifier-external-validations/validation-1')) {
        return jsonResponse(externalValidation)
      }
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp('/projects/project-1')

    expect(await screen.findByText('GSE140494 to GSE32646 pCR validation')).toBeInTheDocument()
    expect(screen.getByText(/External ROC-AUC 0.619/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: 'Open results dashboard' }))

    expect(await screen.findByRole('heading', {
      name: 'GSE140494 to GSE32646 pCR validation',
    })).toBeInTheDocument()
    expect(screen.getAllByText('Success criteria not met').length).toBeGreaterThan(0)
    expect(screen.getByRole('table', { name: 'Prespecified success criteria' })).toBeInTheDocument()
    expect(screen.getByText(/74 samples were predicted pCR/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /run/i })).not.toBeInTheDocument()
  })

  it('requires the exact project name before deleting a project', async () => {
    let deleted = false
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/projects/project-1') && init?.method === 'DELETE') {
        deleted = true
        return new Response(null, { status: 204 })
      }
      if (url.endsWith('/projects')) return jsonResponse(deleted ? [] : [project])
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp('/projects')

    fireEvent.click(await screen.findByRole('button', { name: 'Delete Airway study' }))
    const confirm = screen.getByRole('button', { name: 'Delete project' })
    expect(confirm).toBeDisabled()
    fireEvent.change(screen.getByRole('textbox', { name: 'Project name' }), {
      target: { value: 'Airway study' },
    })
    expect(confirm).toBeEnabled()
    fireEvent.click(confirm)

    await waitFor(() => expect(screen.queryByText('Airway study')).not.toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/projects/project-1'),
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('uploads a checksum-frozen signature definition from the project page', async () => {
    let uploaded = false
    let uploadName: FormDataEntryValue | null = null
    let uploadIdentifierType: FormDataEntryValue | null = null
    const definition = {
      id: 'definition-1', project_id: 'project-1', name: 'Cartilage response',
      description: null, definition_format: 'gene_list', identifier_type: 'ensembl_gene_id',
      original_name: 'cartilage.tsv', source_sha256: 'a'.repeat(64), source_size_bytes: 32,
      manifest_sha256: 'b'.repeat(64), set_count: 1, requested_identifier_count: 3,
      unique_identifier_count: 3, duplicate_identifier_count: 0, weighted: true,
      created_at: '2026-07-16T00:00:00Z', updated_at: '2026-07-16T00:00:00Z',
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/projects/project-1')) return jsonResponse(project)
      if (url.endsWith('/projects/project-1/datasets')) return jsonResponse([])
      if (url.endsWith('/projects/project-1/signature-definitions') && init?.method === 'POST') {
        const form = init.body as FormData
        uploadName = form.get('name')
        uploadIdentifierType = form.get('identifier_type')
        uploaded = true
        return jsonResponse(definition, 201)
      }
      if (url.endsWith('/projects/project-1/signature-definitions')) {
        return jsonResponse(uploaded ? [definition] : [])
      }
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    const view = renderApp('/projects/project-1')
    expect(await screen.findByRole('heading', { name: 'Reusable signature definitions' })).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Signature name' }), {
      target: { value: 'Cartilage response' },
    })
    const fileInput = view.container.querySelector<HTMLInputElement>('input[type="file"]')
    expect(fileInput).not.toBeNull()
    fireEvent.change(fileInput as HTMLInputElement, {
      target: { files: [new File(['gene_id\tweight\nTP53\t1\n'], 'cartilage.tsv')] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Upload signature definition' }))

    expect(await screen.findByText(/3 unique identifiers/)).toBeInTheDocument()
    expect(uploadName).toBe('Cartilage response')
    expect(uploadIdentifierType).toBe('ensembl_gene_id')
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

  it('stops an active Expression Bundle preparation from the project dashboard', async () => {
    let preparationState = 'RUNNING'
    const preparationRun = {
      ...completedRun,
      id: 'run-preparation',
      run_type: 'dataset_preparation',
      state: preparationState,
      exit_code: null,
      finished_at: null,
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/projects/project-1')) return jsonResponse(project)
      if (url.endsWith('/projects/project-1/datasets')) return jsonResponse([dataset])
      if (url.endsWith('/datasets/dataset-1/validation-runs')) return jsonResponse([completedRun])
      if (url.endsWith('/datasets/dataset-1/preparation-runs')) {
        return jsonResponse([{ ...preparationRun, state: preparationState }])
      }
      if (url.endsWith('/datasets/dataset-1/prepared-versions')) return jsonResponse([])
      if (url.endsWith('/runs/run-1')) return jsonResponse(completedRun)
      if (url.endsWith('/runs/run-1/artifacts')) return jsonResponse([])
      if (url.endsWith('/runs/run-preparation/cancel') && init?.method === 'POST') {
        preparationState = 'CANCELLING'
        return jsonResponse({ ...preparationRun, state: preparationState }, 202)
      }
      if (url.endsWith('/runs/run-preparation')) {
        return jsonResponse({ ...preparationRun, state: preparationState })
      }
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp('/projects/project-1')

    fireEvent.click(await screen.findByRole('button', { name: 'Stop run' }))
    expect(await screen.findByRole('button', { name: 'Stopping…' })).toBeDisabled()
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/runs/run-preparation/cancel'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('validates a paired FASTQ sample sheet against the pinned reference', async () => {
    const rawDataset = {
      ...dataset,
      id: 'dataset-fastq',
      name: 'Tiny paired FASTQ study',
      source_kind: 'fastq',
      annotation_release: 'GENCODE 50',
      status: 'draft',
    }
    const file = (role: 'sample_sheet' | 'fastq_r1' | 'fastq_r2', name: string) => ({
      dataset_file_id: `${role}-${name}`,
      role,
      original_name: name,
      storage_uri: `local://${name}`,
      size_bytes: 128,
      sha256: role === 'sample_sheet' ? 'c'.repeat(64) : 'd'.repeat(64),
    })
    const ingestion = {
      schema_version: '1.1.0',
      dataset_id: 'dataset-fastq',
      organism: 'Homo sapiens',
      genome_build: 'GRCh38',
      source_kind: 'fastq',
      reference: {
        reference_id: 'gencode_v50_grch38_salmon_1_11_4',
        definition_sha256: 'a'.repeat(64),
        name: 'GENCODE 50 GRCh38.p14 full-genome-decoy Salmon reference',
        annotation_release: 'GENCODE 50',
        salmon_version: '1.11.4',
      },
      sample_sheet: file('sample_sheet', 'samples.tsv'),
      library_layout: 'paired_end',
      strandedness: 'auto',
      sample_count: 1,
      lane_count: 1,
      read_file_count: 2,
      samples: [{
        sample_id: 'sample_A',
        lanes: [{
          lane_id: 'lane_1',
          read1: file('fastq_r1', 'sample_A_R1.fastq.gz'),
          read2: file('fastq_r2', 'sample_A_R2.fastq.gz'),
        }],
        metadata: { condition: 'control' },
      }],
      warnings: [],
    }
    let ingestBody: Record<string, unknown> | null = null
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/projects/project-1')) return jsonResponse(project)
      if (url.endsWith('/projects/project-1/datasets')) return jsonResponse([rawDataset])
      if (url.endsWith('/datasets/dataset-fastq/files')) {
        return jsonResponse([
          { ...file('fastq_r1', 'sample_A_R1.fastq.gz'), id: 'r1', dataset_id: 'dataset-fastq', created_at: '2026-07-16T00:00:00Z' },
          { ...file('fastq_r2', 'sample_A_R2.fastq.gz'), id: 'r2', dataset_id: 'dataset-fastq', created_at: '2026-07-16T00:00:00Z' },
        ])
      }
      if (url.endsWith('/datasets/dataset-fastq/raw-rnaseq/ingestion')) {
        return jsonResponse(null)
      }
      if (url.endsWith('/datasets/dataset-fastq/raw-rnaseq/ingest') && init?.method === 'POST') {
        ingestBody = JSON.parse(String(init.body)) as Record<string, unknown>
        return jsonResponse(ingestion, 201)
      }
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp('/projects/project-1')

    expect(await screen.findByText('Tiny paired FASTQ study')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'R1 FASTQ' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'R2 FASTQ' })).toBeInTheDocument()
    expect(screen.getByText(/GENCODE 50, GRCh38.p14, Salmon 1.11.4/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run QC & quantify' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Validate sample sheet' }))

    expect(await screen.findByText(/VALID: 1 paired-end samples/)).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Raw RNA-seq sample sheet preview' })).toBeInTheDocument()
    expect(screen.getByText('condition=control')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run QC & quantify' })).toBeEnabled()
    expect(ingestBody).toEqual({ strandedness: 'auto' })
  })

  it('validates Affymetrix CEL inputs with an explicit platform and aggregation policy', async () => {
    const microarrayDataset = {
      ...dataset,
      id: 'dataset-cel',
      name: 'Cartilage Human Gene arrays',
      modality: 'microarray',
      source_kind: 'affymetrix_cel',
      annotation_release: null,
      status: 'draft',
    }
    const platform = {
      platform_id: 'affymetrix_hugene_1_0_st_v1',
      definition_sha256: 'a'.repeat(64),
      adapter_version: '1.0.0',
      vendor: 'Affymetrix',
      array_design: 'Human Gene 1.0 ST Array',
      organism: 'Homo sapiens',
      chip_type_aliases: ['HuGene-1_0-st-v1'],
      cel_formats: ['calvin'],
      normalization: {
        engine: 'oligo', method: 'rma', target: 'probeset',
        pd_info_package: 'pd.hugene.1.0.st.v1',
      },
      annotation: {
        package: 'hugene10sttranscriptcluster.db', probe_key: 'PROBEID',
        gene_id_field: 'ENSEMBL', gene_symbol_field: 'SYMBOL',
        confidence: 'explicit_platform_adapter',
      },
      aggregation: {
        default_method: 'highest_mad', supported_methods: ['highest_mad', 'median', 'mean'],
      },
      sources: [],
    }
    const celFile = {
      dataset_file_id: 'cel-1', role: 'cel_file', original_name: 'sample_A.CEL.gz',
      storage_uri: 'local://sample_A.CEL.gz', size_bytes: 1024, sha256: 'b'.repeat(64),
    }
    const metadataFile = {
      dataset_file_id: 'metadata-1', role: 'sample_metadata', original_name: 'samples.tsv',
      storage_uri: 'local://samples.tsv', size_bytes: 128, sha256: 'c'.repeat(64),
    }
    const ingestion = {
      schema_version: '1.0.0', dataset_id: 'dataset-cel', organism: 'Homo sapiens',
      source_kind: 'affymetrix_cel',
      platform: {
        ...platform,
        detected_chip_type: 'HuGene-1_0-st-v1', cel_format: 'calvin',
      },
      aggregation_method: 'highest_mad', sample_metadata: metadataFile,
      sample_count: 1, cel_file_count: 1,
      samples: [{ sample_id: 'sample_A', cel_file: celFile, metadata: { condition: 'control' } }],
      warnings: [],
    }
    let ingestBody: Record<string, unknown> | null = null
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/projects/project-1')) return jsonResponse(project)
      if (url.endsWith('/projects/project-1/datasets')) return jsonResponse([microarrayDataset])
      if (url.endsWith('/microarray-platforms')) return jsonResponse([platform])
      if (url.endsWith('/datasets/dataset-cel/files')) {
        return jsonResponse([
          { ...celFile, id: 'cel-1', dataset_id: 'dataset-cel', created_at: '2026-07-16T00:00:00Z' },
          { ...metadataFile, id: 'metadata-1', dataset_id: 'dataset-cel', created_at: '2026-07-16T00:00:00Z' },
        ])
      }
      if (url.endsWith('/datasets/dataset-cel/microarray/ingestion')) return jsonResponse(null)
      if (url.endsWith('/datasets/dataset-cel/microarray/ingest') && init?.method === 'POST') {
        ingestBody = JSON.parse(String(init.body)) as Record<string, unknown>
        return jsonResponse(ingestion, 201)
      }
      if (url.endsWith('/datasets/dataset-cel/preparation-runs')) return jsonResponse([])
      if (url.endsWith('/datasets/dataset-cel/prepared-versions')) return jsonResponse([])
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp('/projects/project-1')

    expect(await screen.findByText('Cartilage Human Gene arrays')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'CEL files' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sample metadata' })).toBeInTheDocument()
    expect(await screen.findByText(/oligo RMA · annotation hugene10sttranscriptcluster.db/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run RMA & prepare' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Validate CEL inputs' }))

    expect(await screen.findByText(/VALID: 1 samples and 1 checksum-frozen CEL files/)).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Affymetrix CEL sample metadata preview' })).toBeInTheDocument()
    expect(screen.getByText('condition=control')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run RMA & prepare' })).toBeEnabled()
    expect(ingestBody).toEqual({
      platform_id: 'affymetrix_hugene_1_0_st_v1',
      aggregation_method: 'highest_mad',
    })
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
          value_types_available: ['raw_counts', 'log_expression', 'tpm'],
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
      if (url.endsWith('/projects/project-1/signature-definitions')) {
        return jsonResponse([{
          id: 'definition-1', project_id: 'project-1', name: 'Cartilage response',
          description: null, definition_format: 'gene_list', identifier_type: 'ensembl_gene_id',
          original_name: 'cartilage.tsv', source_sha256: 'a'.repeat(64), source_size_bytes: 32,
          manifest_sha256: 'b'.repeat(64), set_count: 1, requested_identifier_count: 3,
          unique_identifier_count: 3, duplicate_identifier_count: 0, weighted: true,
          created_at: '2026-07-16T00:00:00Z', updated_at: '2026-07-16T00:00:00Z',
        }])
      }
      if (url.endsWith('/prepared-datasets/prepared-1/signature-mappings')) {
        return jsonResponse([{
          id: 'mapping-1', signature_definition_id: 'definition-1',
          prepared_dataset_id: 'prepared-1', report_sha256: 'c'.repeat(64),
          missing_sha256: 'd'.repeat(64), ambiguous_sha256: 'e'.repeat(64),
          requested_identifier_count: 3, unique_identifier_count: 3,
          mapped_identifier_count: 2, missing_identifier_count: 1,
          ambiguous_identifier_count: 0, duplicate_identifier_count: 0,
          mapping_coverage: 2 / 3,
          report_json: {
            sets: [{
              mapped_entries: [
                { identifier: 'TP53', feature_id: 'ENSG000001', weight: 1.5 },
                { identifier: 'EGFR', feature_id: 'ENSG000002', weight: -0.5 },
              ],
            }],
          },
          created_at: '2026-07-16T00:00:00Z', updated_at: '2026-07-16T00:00:00Z',
        }])
      }
      if (url.endsWith('/prepared-datasets/prepared-1/deconvolution/methods')) {
        return jsonResponse(deconvolutionCapabilities)
      }
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp('/prepared-datasets/prepared-1')

    expect(await screen.findByRole('heading', { name: 'Expression Bundle' })).toBeInTheDocument()
    expect(await screen.findByText('100.0%')).toBeInTheDocument()
    expect(await screen.findByText('sample_1')).toBeInTheDocument()
    expect(screen.getByText(/42 total · 1 detected/)).toBeInTheDocument()
    expect(screen.getByText('5 mapped')).toBeInTheDocument()
    expect(await screen.findByText('Mapping coverage: 66.7%')).toBeInTheDocument()
    expect(screen.getByText('1 missing')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Missing identifiers/ })).toHaveAttribute(
      'href',
      expect.stringContaining('/signature-mappings/mapping-1/missing.tsv'),
    )
    expect(screen.getByRole('button', { name: 'Score signature' })).toBeEnabled()
    expect(screen.getByRole('combobox', { name: 'Scoring method' })).toHaveTextContent(
      'Mean z-score · recommended',
    )
    expect(screen.getByText(/below the 80% recommendation threshold/i)).toBeInTheDocument()
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Scoring method' }))
    fireEvent.click(await screen.findByRole('option', { name: 'GSVA (Bioconductor R)' }))
    expect(screen.getByRole('spinbutton', { name: 'Minimum set size' })).toHaveValue(1)
    expect(screen.getByRole('combobox', { name: 'Kernel' })).toHaveTextContent('Gaussian')
    expect(screen.getByText(/pinned R environment/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Configure cell-type deconvolution' })).toBeInTheDocument()
    expect(await screen.findByRole('combobox', { name: 'Deconvolution method' })).toHaveTextContent('quanTIseq')
    expect(screen.getByText('Cell fractions')).toBeInTheDocument()
    expect(screen.getByText('Runner available')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save deconvolution design' })).toBeEnabled()
    expect(screen.getByRole('heading', { name: 'Import CIBERSORTx relative fractions' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Choose result table' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Validate and import result' })).toBeDisabled()
  })

  it('renders deterministic signature scores with mapping evidence and downloads', async () => {
    const analysis = {
      id: 'signature-analysis-1', project_id: 'project-1', prepared_dataset_id: 'prepared-1',
      analysis_type: 'signature', name: 'Cartilage response · mean z score', description: null,
      configuration_json: {
        analysis_type: 'signature', method: 'mean_z_score', assay: 'log_expression',
        parameters: {
          signature_mapping_id: 'mapping-1', minimum_gene_set_size: 1,
          maximum_gene_set_size: 5000, gsva_kcdf: 'Gaussian', gsva_tau: 1,
          gsva_max_diff: true, gsva_abs_ranking: false, ssgsea_alpha: 0.25,
          ssgsea_normalize: true,
        }, random_seed: 0,
        signature_mapping_report_sha256: 'c'.repeat(64),
        signature_definition_id: 'definition-1', mapping_coverage: 2 / 3,
      },
      created_at: '2026-07-16T00:00:00Z',
    }
    const run = {
      ...completedRun, id: 'signature-run-1', run_type: 'analysis', dataset_id: 'dataset-1',
      prepared_dataset_id: 'prepared-1', analysis_id: 'signature-analysis-1',
    }
    const scores = {
      schema_version: '1.1.0', analysis_id: analysis.id, prepared_dataset_id: 'prepared-1',
      method: 'mean_z_score', assay: 'log_expression',
      formula: 'Arithmetic mean of mapped gene z-scores.', sample_count: 2, set_count: 1,
      signature_mapping: {
        id: 'mapping-1', report_sha256: 'c'.repeat(64),
        signature_definition_id: 'definition-1', signature_definition_sha256: 'b'.repeat(64),
        expression_bundle_sha256: 'a'.repeat(64), mapping_coverage: 2 / 3,
        requested_identifier_count: 3, mapped_identifier_count: 2,
        missing_identifier_count: 1, ambiguous_identifier_count: 0,
        duplicate_identifier_count: 0,
      },
      sets: [{
        signature_id: 'set-1', name: 'Cartilage response', requested_identifier_count: 3,
        mapped_identifier_count: 2, scored_feature_count: 2,
        excluded_constant_feature_count: 0, mapping_coverage: 2 / 3,
        score_minimum: -0.75, score_maximum: 0.75, score_mean: 0,
        scores: [
          { sample_id: 'sample_A', score: -0.75, metadata: { condition: 'control' } },
          { sample_id: 'sample_B', score: 0.75, metadata: { condition: 'treated' } },
        ],
      }],
      phenotype_association: {
        phenotype_column: 'condition', phenotype_kind: 'categorical', covariates: [],
        block_column: null, formula: 'score ~ condition',
        design_matrix_columns: ['Intercept', 'condition[treated]'],
        associations: [{
          signature_id: 'set-1', signature_name: 'Cartilage response',
          test: 'adjusted_two_group_comparison', sample_count: 2, effect: 1.5,
          statistic: 4.2, degrees_of_freedom: 1, p_value: 0.03,
          adjusted_p_value: 0.03, correlation: null,
          group_summaries: [
            { level: 'control', sample_count: 1, score_mean: -0.75 },
            { level: 'treated', sample_count: 1, score_mean: 0.75 },
          ],
        }],
      },
      warnings: ['Mapping report contains 1 missing identifier(s).'],
      software: {
        language: 'Python', language_version: '3.12.11',
        implementation: 'transcriptforge_analysis.signature_scoring',
        packages: { numpy: '2.3.1', scipy: '1.16.0' },
      },
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/analyses/signature-analysis-1')) return jsonResponse(analysis)
      if (url.endsWith('/analyses/signature-analysis-1/runs')) return jsonResponse([run])
      if (url.endsWith('/prepared-datasets/prepared-1')) {
        return jsonResponse({
          id: 'prepared-1', dataset_id: 'dataset-1', version: 1,
          preparation_run_id: 'preparation-run-1', value_types_available: ['log_expression'],
          sample_count: 2, feature_count: 100, qc_status: 'PASS',
          created_at: '2026-07-16T00:00:00Z',
        })
      }
      if (url.endsWith('/runs/signature-run-1/signature-scores')) return jsonResponse(scores)
      if (url.endsWith('/runs/signature-run-1/result-manifest')) {
        return jsonResponse({
          schema_version: '1.0.0', analysis_type: 'signature', title: 'Signature scoring',
          summary_metrics: [], sections: [], downloads: [], warnings: scores.warnings,
        })
      }
      if (url.endsWith('/runs/signature-run-1/artifacts')) {
        return jsonResponse([{
          id: 'score-table', run_id: run.id, artifact_type: 'signature_scores_table',
          title: 'Per-sample signature scores table', relative_path: 'signature_scores.tsv',
          mime_type: 'text/tab-separated-values', size_bytes: 128, sha256: 'd'.repeat(64),
          display_order: 2, metadata_json: {},
        }])
      }
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp('/analyses/signature-analysis-1')

    expect(await screen.findByRole('heading', { name: 'Cartilage response · mean z score' })).toBeInTheDocument()
    expect(await screen.findByText('Mapped / requested')).toBeInTheDocument()
    expect(screen.getByText('2/3')).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Cartilage response per-sample scores' })).toBeInTheDocument()
    expect(screen.getByText('condition=treated')).toBeInTheDocument()
    expect(screen.getByText(/1 missing identifier/)).toBeInTheDocument()
    expect(screen.getByText(/numpy 2.3.1/)).toBeInTheDocument()
    expect(screen.getByText(/Do not compare raw signature-score magnitudes/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Scores by condition' })).toBeInTheDocument()
    expect(screen.getByText('FDR 0.03')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Scores by condition' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Per-sample signature scores table/ })).toHaveAttribute(
      'href', expect.stringContaining('/artifacts/score-table/download'),
    )
  })

  it('shows classifier leakage evidence and completed OOF results', async () => {
    const fold = {
      repeat: 1, fold: 1, training_sample_count: 16, test_sample_count: 8,
      training_class_counts: { control: 8, treated: 8 },
      test_class_counts: { control: 4, treated: 4 },
      training_group_count: 8, test_group_count: 4, group_overlap_count: 0,
    }
    const analysis = {
      id: 'classifier-analysis-1', project_id: 'project-1', prepared_dataset_id: 'prepared-1',
      analysis_type: 'classifier', name: 'Treated elastic-net classifier', description: null,
      configuration_json: {
        analysis_type: 'classifier', method: 'elastic_net', assay: 'log_expression',
        parameters: {
          outcome_column: 'condition', positive_class: 'treated', group_column: 'subject_id',
          cohort_column: 'cohort', validation_mode: 'repeated_nested_cross_validation',
          feature_filter: 'top_variance', top_variable_features: 500,
          class_weight: 'balanced', outer_folds: 3, inner_folds: 2, repeats: 2,
          primary_metric: 'roc_auc', probability_calibration: 'none',
          decision_threshold_strategy: 'fixed_0_5', bootstrap_iterations: 1000,
          permutation_count: 100,
        },
        random_seed: 20260717,
        design_validation: {
          valid: true, method: 'elastic_net', assay: 'log_expression',
          outcome_column: 'condition', negative_class: 'control', positive_class: 'treated',
          eligible_sample_count: 24, class_counts: { control: 12, treated: 12 },
          group_column: 'subject_id', group_count: 12, cohort_column: 'cohort',
          outer_folds: 3, inner_folds: 2, repeats: 2, expected_oof_prediction_count: 48,
          preprocessing_scope: 'fit_inside_each_training_fold',
          tuning_scope: 'inner_training_folds_only', fold_plan: [fold],
          errors: [], warnings: ['Internal validation only.'],
        },
        execution_available: true,
        leakage_policy: {
          preprocessing_scope: 'fit_inside_each_training_fold',
          feature_selection_scope: 'fit_inside_each_training_fold',
          hyperparameter_tuning_scope: 'inner_training_folds_only',
          outer_test_fold_role: 'evaluation_only',
        },
      },
      created_at: '2026-07-18T00:00:00Z',
    }
    const run = {
      ...completedRun, id: 'classifier-run-1', run_type: 'analysis', dataset_id: 'dataset-1',
      prepared_dataset_id: 'prepared-1', analysis_id: analysis.id,
    }
    const results = {
      schema_version: '1.0.0', analysis_id: analysis.id, prepared_dataset_id: 'prepared-1',
      method: 'elastic_net', assay: 'log_expression',
      outcome: {
        column: 'condition', negative_class: 'control', positive_class: 'treated',
        class_counts: { control: 12, treated: 12 },
      },
      validation: {
        mode: 'repeated_nested_cross_validation', group_column: 'subject_id',
        cohort_column: 'cohort', outer_folds: 3, inner_folds: 2, repeats: 2,
        primary_metric: 'roc_auc', probability_calibration: 'none',
        decision_threshold_strategy: 'fixed_0_5',
      },
      sample_count: 24, input_feature_count: 1000, top_variable_features: 500,
      oof_coverage: {
        expected_prediction_count: 48, observed_prediction_count: 48,
        one_prediction_per_sample_per_repeat: true,
      },
      metrics: { roc_auc: 0.94, pr_auc: 0.92, balanced_accuracy: 0.88, brier_score: 0.12 },
      repeat_metrics: [
        { repeat: 1, roc_auc: 0.93, pr_auc: 0.91, balanced_accuracy: 0.87, brier_score: 0.13 },
        { repeat: 2, roc_auc: 0.95, pr_auc: 0.93, balanced_accuracy: 0.89, brier_score: 0.11 },
      ],
      confidence_intervals: {
        method: 'experimental_unit_percentile_bootstrap', iterations: 1000,
        confidence_level: 0.95,
        intervals: {
          roc_auc: { lower: 0.88, upper: 0.98 },
          pr_auc: { lower: 0.86, upper: 0.97 },
          balanced_accuracy: { lower: 0.8, upper: 0.94 },
          brier_score: { lower: 0.08, upper: 0.17 },
        },
      },
      diagnostic_curves: {
        roc_curve: [], precision_recall_curve: [], calibration_curve: [],
        calibration_intercept: -0.04, calibration_slope: 0.97,
        confusion_matrix: { true_negative: 21, false_positive: 3, false_negative: 3, true_positive: 21 },
      },
      permutation_control: {
        method: 'full_nested_cross_validation_label_permutation', count: 100,
        roc_auc_values: [], mean_roc_auc: 0.5, empirical_p_value: 0.0099,
      },
      learning_curve: [],
      model_comparisons: [
        { method: 'elastic_net', role: 'primary_locked_model', metrics: { roc_auc: 0.94, pr_auc: 0.92, balanced_accuracy: 0.88, brier_score: 0.12 }, tuning_scope: 'inner_training_folds_only' },
        { method: 'random_forest', role: 'comparison_only_not_exported', metrics: { roc_auc: 0.9, pr_auc: 0.88, balanced_accuracy: 0.82, brier_score: 0.16 }, tuning_scope: 'inner_training_folds_only' },
        { method: 'hist_gradient_boosting', role: 'comparison_only_not_exported', metrics: { roc_auc: 0.91, pr_auc: 0.89, balanced_accuracy: 0.83, brier_score: 0.15 }, tuning_scope: 'inner_training_folds_only' },
      ],
      folds: [{ ...fold, selected_feature_count: 500, nonzero_feature_count: 18,
        best_c: 0.5, best_l1_ratio: 0.5, decision_threshold: 0.5 }],
      feature_stability: [{
        feature_id: 'ENSG000001', selection_frequency: 1, nonzero_frequency: 0.83,
        mean_coefficient: 1.245,
      }],
      locked_model: {
        path: 'model.json', feature_schema_path: 'inference_schema.json',
        model_card_path: 'model_card.json', inference_example_path: 'inference_example.tsv',
      },
      leakage_audit: { all_fold_scopes_disjoint: true }, warnings: [],
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/analyses/classifier-analysis-1/runs')) return jsonResponse([run])
      if (url.endsWith('/analyses/classifier-analysis-1')) return jsonResponse(analysis)
      if (url.endsWith('/runs/classifier-run-1/classifier-results')) return jsonResponse(results)
      if (url.endsWith('/runs/classifier-run-1/result-manifest')) {
        return jsonResponse({
          schema_version: '1.0.0', analysis_type: 'classifier', title: 'Classifier',
          summary_metrics: [], sections: [], downloads: [], warnings: [],
        })
      }
      if (url.endsWith('/runs/classifier-run-1/artifacts')) return jsonResponse([])
      if (url.endsWith('/prepared-datasets/prepared-1')) {
        return jsonResponse({
          id: 'prepared-1', dataset_id: 'dataset-1', version: 1,
          preparation_run_id: 'preparation-run-1', value_types_available: ['log_expression'],
          sample_count: 24, feature_count: 1000, qc_status: 'PASS',
          created_at: '2026-07-18T00:00:00Z',
        })
      }
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp('/analyses/classifier-analysis-1')

    expect(await screen.findByRole('heading', {
      name: 'Treated elastic-net classifier',
    })).toBeInTheDocument()
    expect(screen.getByText('48')).toBeInTheDocument()
    expect(screen.getByText('inner training folds only')).toBeInTheDocument()
    expect(screen.getByRole('table', {
      name: 'Saved classifier outer-fold audit',
    })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run again' })).toBeEnabled()
    expect(await screen.findByRole('heading', {
      name: 'Internal validation results',
    })).toBeInTheDocument()
    expect(screen.getByText('0.940')).toBeInTheDocument()
    expect(screen.getByText(/48 of 48 planned OOF predictions/)).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Classifier metrics by repeat' })).toBeInTheDocument()
    expect(screen.getByText(/empirical p = 0.0099/)).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Classifier feature stability' })).toBeInTheDocument()
    expect(screen.getByText('ENSG000001')).toBeInTheDocument()
  })

  it('renders multinomial OOF metrics, confusion matrix, and class coefficients', async () => {
    const fold = {
      repeat: 1, fold: 1, training_sample_count: 24, test_sample_count: 12,
      training_class_counts: { basal: 8, immune: 8, luminal: 8 },
      test_class_counts: { basal: 4, immune: 4, luminal: 4 },
      training_group_count: 8, test_group_count: 4, group_overlap_count: 0,
    }
    const analysis = {
      id: 'multiclass-analysis-1', project_id: 'project-1', prepared_dataset_id: 'prepared-1',
      analysis_type: 'classifier', name: 'Tumor subtype classifier', description: null,
      configuration_json: {
        analysis_type: 'classifier', method: 'multinomial_elastic_net', assay: 'log_expression',
        parameters: {
          outcome_column: 'subtype', positive_class: null, group_column: 'subject_id',
          cohort_column: 'cohort', validation_mode: 'repeated_nested_cross_validation',
          feature_filter: 'top_variance', top_variable_features: 500, class_weight: 'balanced',
          outer_folds: 3, inner_folds: 2, repeats: 2, primary_metric: 'macro_roc_auc',
          probability_calibration: 'none', decision_threshold_strategy: 'fixed_0_5',
          bootstrap_iterations: 1000, permutation_count: 100,
        },
        random_seed: 20260718,
        design_validation: {
          valid: true, method: 'multinomial_elastic_net', assay: 'log_expression',
          outcome_column: 'subtype', negative_class: null, positive_class: null,
          class_labels: ['basal', 'immune', 'luminal'], eligible_sample_count: 36,
          class_counts: { basal: 12, immune: 12, luminal: 12 }, group_column: 'subject_id',
          group_count: 12, cohort_column: 'cohort', outer_folds: 3, inner_folds: 2, repeats: 2,
          expected_oof_prediction_count: 72, preprocessing_scope: 'fit_inside_each_training_fold',
          tuning_scope: 'inner_training_folds_only', fold_plan: [fold], errors: [], warnings: [],
        },
        execution_available: true,
        leakage_policy: {
          preprocessing_scope: 'fit_inside_each_training_fold',
          feature_selection_scope: 'fit_inside_each_training_fold',
          hyperparameter_tuning_scope: 'inner_training_folds_only',
          outer_test_fold_role: 'evaluation_only',
        },
      },
      created_at: '2026-07-18T00:00:00Z',
    }
    const run = {
      ...completedRun, id: 'multiclass-run-1', run_type: 'analysis', dataset_id: 'dataset-1',
      prepared_dataset_id: 'prepared-1', analysis_id: analysis.id,
    }
    const results = {
      schema_version: '1.0.0', analysis_id: analysis.id, prepared_dataset_id: 'prepared-1',
      method: 'multinomial_elastic_net', assay: 'log_expression',
      outcome: {
        column: 'subtype', classes: ['basal', 'immune', 'luminal'],
        class_counts: { basal: 12, immune: 12, luminal: 12 },
      },
      validation: {
        mode: 'repeated_nested_cross_validation', group_column: 'subject_id',
        cohort_column: 'cohort', outer_folds: 3, inner_folds: 2, repeats: 2,
        primary_metric: 'macro_roc_auc', prediction_rule: 'maximum_class_probability',
      },
      sample_count: 36, input_feature_count: 1000, top_variable_features: 500,
      oof_coverage: {
        expected_prediction_count: 72, observed_prediction_count: 72,
        one_prediction_per_sample_per_repeat: true,
      },
      metrics: {
        macro_roc_auc: 0.96, macro_f1: 0.9, balanced_accuracy: 0.91,
        accuracy: 0.91, log_loss: 0.22,
      },
      repeat_metrics: [],
      confidence_intervals: {
        method: 'experimental_unit_percentile_bootstrap', iterations: 1000,
        confidence_level: 0.95, intervals: { macro_roc_auc: { lower: 0.9, upper: 0.99 } },
      },
      diagnostics: {
        one_vs_rest_roc_curves: {}, class_order: ['basal', 'immune', 'luminal'],
        confusion_matrix: [[22, 1, 1], [1, 22, 1], [0, 2, 22]],
      },
      permutation_control: {
        method: 'full_nested_cross_validation_label_permutation', count: 100,
        macro_roc_auc_values: [], mean_macro_roc_auc: 0.5, empirical_p_value: 0.0099,
      },
      folds: [],
      feature_stability: [{
        feature_id: 'ESR1', class_label: 'luminal', selection_frequency: 1,
        nonzero_frequency: 0.9, mean_coefficient: 1.2,
      }],
      leakage_audit: { all_fold_scopes_disjoint: true },
      locked_model: {
        path: 'model.json', feature_schema_path: 'inference_schema.json',
        model_card_path: 'model_card.json', inference_example_path: 'inference_example.tsv',
      },
      warnings: [],
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/analyses/multiclass-analysis-1/runs')) return jsonResponse([run])
      if (url.endsWith('/analyses/multiclass-analysis-1')) return jsonResponse(analysis)
      if (url.endsWith('/runs/multiclass-run-1/classifier-results')) return jsonResponse(results)
      if (url.endsWith('/runs/multiclass-run-1/result-manifest')) return jsonResponse({
        schema_version: '1.0.0', analysis_type: 'classifier', title: 'Classifier',
        summary_metrics: [], sections: [], downloads: [], warnings: [],
      })
      if (url.endsWith('/runs/multiclass-run-1/artifacts')) return jsonResponse([])
      if (url.endsWith('/prepared-datasets/prepared-1')) return jsonResponse({
        id: 'prepared-1', dataset_id: 'dataset-1', version: 1,
        preparation_run_id: 'preparation-run-1', value_types_available: ['log_expression'],
        sample_count: 36, feature_count: 1000, qc_status: 'PASS',
        created_at: '2026-07-18T00:00:00Z',
      })
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp('/analyses/multiclass-analysis-1')
    expect(await screen.findByRole('heading', {
      name: 'Internal multiclass validation results',
    })).toBeInTheDocument()
    expect(screen.getByText('0.960 (0.900–0.990)')).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Multiclass confusion matrix' })).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Multiclass feature stability' })).toBeInTheDocument()
    expect(screen.getByText('ESR1')).toBeInTheDocument()
  })

  it('keeps saved deconvolution semantics visible while its runner is pending', async () => {
    const analysis = {
      id: 'deconvolution-analysis-1', project_id: 'project-1', prepared_dataset_id: 'prepared-1',
      analysis_type: 'deconvolution', name: 'EPIC cell composition', description: null,
      configuration_json: {
        analysis_type: 'deconvolution', method: 'epic', assay: 'tpm',
        parameters: { reference_profile: 'TRef', minimum_gene_overlap: 0.5 },
        random_seed: 0, method_registry_version: '2026.07.0',
        method_registry_sha256: 'f'.repeat(64),
        method_spec: deconvolutionCapabilities.methods[0].method,
        input_assay_descriptor: {
          name: 'tpm', scale: 'linear', value_type: 'nonnegative_continuous',
          feature_level: 'gene', sha256: 'c'.repeat(64),
        },
        result_type: 'cell_fraction', execution_available: false,
      },
      created_at: '2026-07-18T00:00:00Z',
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/analyses/deconvolution-analysis-1/runs')) return jsonResponse([])
      if (url.endsWith('/analyses/deconvolution-analysis-1')) return jsonResponse(analysis)
      if (url.endsWith('/prepared-datasets/prepared-1')) {
        return jsonResponse({
          id: 'prepared-1', dataset_id: 'dataset-1', version: 1,
          preparation_run_id: 'preparation-run-1', value_types_available: ['tpm'],
          sample_count: 4, feature_count: 1000, qc_status: 'PASS',
          created_at: '2026-07-18T00:00:00Z',
        })
      }
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp('/analyses/deconvolution-analysis-1')

    expect(await screen.findByRole('heading', { name: 'EPIC cell composition' })).toBeInTheDocument()
    expect(screen.getByText('Cell fractions')).toBeInTheDocument()
    expect(screen.getByText('bounded sum')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Runner unavailable' })).toBeDisabled()
    expect(screen.getByText(/must never be relabeled or normalized into one another/i)).toBeInTheDocument()
  })

  it('renders completed quanTIseq fractions with overlap evidence and downloads', async () => {
    const method = deconvolutionCapabilities.methods[1].method
    const analysis = {
      id: 'quantiseq-analysis-1', project_id: 'project-1', prepared_dataset_id: 'prepared-1',
      analysis_type: 'deconvolution', name: 'quanTIseq cell composition', description: null,
      configuration_json: {
        analysis_type: 'deconvolution', method: 'quantiseq', assay: 'tpm',
        parameters: {
          reference_profile: 'TIL10', minimum_gene_overlap: 0.5,
          tumor_mode: false, scale_mrna: true,
        },
        random_seed: 0, method_registry_version: '2026.07.1',
        method_registry_sha256: 'f'.repeat(64), method_spec: method,
        input_assay_descriptor: {
          name: 'tpm', scale: 'linear', value_type: 'nonnegative_continuous',
          feature_level: 'gene', sha256: 'c'.repeat(64),
        },
        result_type: 'cell_fraction', execution_available: true,
      },
      created_at: '2026-07-18T00:00:00Z',
    }
    const run = {
      ...completedRun, id: 'quantiseq-run-1', run_type: 'analysis',
      prepared_dataset_id: 'prepared-1', analysis_id: 'quantiseq-analysis-1',
    }
    const cellTypes = [
      { id: 'B.cells', label: 'B cells' },
      { id: 'Other', label: 'Other / uncharacterized' },
    ]
    const result = {
      schema_version: '1.0.0', analysis_id: analysis.id, prepared_dataset_id: 'prepared-1',
      method: 'quantiseq', result_type: 'cell_fraction', quantity_label: 'Estimated immune-cell fraction',
      unit: 'fraction', composition_constraint: 'sum_to_one_with_other',
      input_validation: {
        input_feature_count: 20000, mapped_feature_count: 19500, blank_symbol_count: 500,
        duplicate_symbol_count: 10, reference_gene_count: 155, overlap_gene_count: 153,
        overlap_fraction: 153 / 155, minimum_overlap_fraction: 0.5, passed: true,
      },
      reference: { id: 'TIL10', version: 'quantiseqr-1.18.0', sha256: 'd'.repeat(64), cell_type_count: 2 },
      cell_types: cellTypes, sample_ids: ['control_1', 'treated_1'],
      estimates: [
        { sample_id: 'control_1', cell_type_id: 'B.cells', value: 0.7 },
        { sample_id: 'control_1', cell_type_id: 'Other', value: 0.3 },
        { sample_id: 'treated_1', cell_type_id: 'B.cells', value: 0.2 },
        { sample_id: 'treated_1', cell_type_id: 'Other', value: 0.8 },
      ],
      composition_summaries: [
        { sample_id: 'control_1', reported_sum: 1, residual_fraction: 0, within_tolerance: true },
        { sample_id: 'treated_1', reported_sum: 1, residual_fraction: 0, within_tolerance: true },
      ],
      warnings: ['Research use only.'],
      software: { language: 'R', language_version: '4.5.0', packages: { quantiseqr: '1.18.0' } },
      provenance: {
        expression_bundle_sha256: 'a'.repeat(64), analysis_request_sha256: 'b'.repeat(64),
        reference_sha256: 'd'.repeat(64),
      },
    }
    const artifact = {
      id: 'fraction-table', run_id: run.id, artifact_type: 'deconvolution_estimates',
      title: 'Long-format cell-fraction estimates', relative_path: 'deconvolution_estimates.tsv',
      mime_type: 'text/tab-separated-values', size_bytes: 123, sha256: 'e'.repeat(64),
      display_order: 2, metadata_json: {},
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith(`/analyses/${analysis.id}/runs`)) return jsonResponse([run])
      if (url.endsWith(`/analyses/${analysis.id}`)) return jsonResponse(analysis)
      if (url.endsWith(`/runs/${run.id}/deconvolution-results`)) return jsonResponse(result)
      if (url.endsWith(`/runs/${run.id}/result-manifest`)) {
        return jsonResponse({ schema_version: '1.0.0', analysis_type: 'deconvolution', title: 'quanTIseq', summary_metrics: [], sections: [], downloads: [], warnings: [] })
      }
      if (url.endsWith(`/runs/${run.id}/artifacts`)) return jsonResponse([artifact])
      if (url.endsWith('/prepared-datasets/prepared-1/deconvolution/comparison')) {
        return jsonResponse({
          schema_version: '1.0.0', prepared_dataset_id: 'prepared-1',
          latest_successful_run_count: 1, sections: [], exclusions: [],
          interpretation: 'Only semantically compatible deconvolution outputs are grouped.',
        })
      }
      if (url.endsWith('/prepared-datasets/prepared-1')) {
        return jsonResponse({
          id: 'prepared-1', dataset_id: 'dataset-1', version: 1,
          preparation_run_id: 'preparation-run-1', value_types_available: ['tpm'],
          sample_count: 2, feature_count: 20000, qc_status: 'PASS',
          created_at: '2026-07-18T00:00:00Z',
        })
      }
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp(`/analyses/${analysis.id}`)

    expect(await screen.findByRole('heading', { name: 'Estimated cell fractions' })).toBeInTheDocument()
    expect(screen.getByText('98.7%')).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'quantiseq cell-population estimates' })).toBeInTheDocument()
    expect(screen.getByText('70.0%')).toBeInTheDocument()
    expect(screen.getByText(/quantiseqr 1.18.0/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Long-format cell-fraction estimates/ })).toHaveAttribute(
      'href', expect.stringContaining('/artifacts/fraction-table/download'),
    )
    expect(screen.getByRole('button', { name: 'Run again' })).toBeEnabled()
  })

  it('renders an imported CIBERSORTx result with external provenance', async () => {
    const method = deconvolutionCapabilities.methods[2].method
    const externalImport = {
      source_filename: 'CIBERSORTx_Results.txt', source_sha256: 'e'.repeat(64),
      source_size_bytes: 512, mode: 'relative', values_declared_as: 'relative_fraction',
      batch_correction: 'B-mode', permutations: 100,
      signature: { name: 'LM22', version: 'custom-2026-07', sha256: 'd'.repeat(64), gene_count: 547 },
      runtime: {
        platform: 'CIBERSORTx', version: 'CIBERSORTx-2026-05',
        external_run_id: 'stanford-job-123', executed_at: '2026-07-17T20:30:00Z',
      },
    }
    const analysis = {
      id: 'cibersortx-analysis-1', project_id: 'project-1', prepared_dataset_id: 'prepared-1',
      analysis_type: 'deconvolution', name: 'Imported CIBERSORTx immune fractions', description: null,
      configuration_json: {
        analysis_type: 'deconvolution', method: 'cibersortx_external', assay: 'tpm',
        parameters: { reference_profile: 'LM22', minimum_gene_overlap: 500 / 547, tumor_mode: false, scale_mrna: false },
        random_seed: 0, method_registry_version: '2026.07.3',
        method_registry_sha256: 'f'.repeat(64), method_spec: method,
        input_assay_descriptor: {
          name: 'tpm', scale: 'linear', value_type: 'nonnegative_continuous',
          feature_level: 'gene', sha256: 'c'.repeat(64),
        },
        result_type: 'cell_fraction', execution_available: false, external_import: externalImport,
      },
      created_at: '2026-07-18T00:00:00Z',
    }
    const run = {
      ...completedRun, id: 'cibersortx-run-1', run_type: 'analysis', profile: 'external_import',
      prepared_dataset_id: 'prepared-1', analysis_id: analysis.id,
    }
    const result = {
      schema_version: '1.0.0', analysis_id: analysis.id, prepared_dataset_id: 'prepared-1',
      method: 'cibersortx_external', method_registry_version: '2026.07.3',
      method_registry_sha256: 'f'.repeat(64), result_type: 'cell_fraction',
      quantity_label: 'Externally estimated relative fraction', unit: 'fraction',
      composition_constraint: 'declared_by_import',
      input_validation: {
        assay: 'tpm', scale: 'linear', value_type: 'nonnegative_continuous',
        feature_level: 'gene', identifier_namespace: 'gene_symbol', input_feature_count: 18000,
        mapped_feature_count: 18000, blank_symbol_count: 0, duplicate_symbol_count: 0,
        reference_gene_count: 547, overlap_gene_count: 500, overlap_fraction: 500 / 547,
        minimum_overlap_fraction: 0, passed: true,
      },
      reference: { id: 'LM22', version: 'custom-2026-07', sha256: 'd'.repeat(64), cell_type_count: 2 },
      cell_types: [{ id: 'B cells', label: 'B cells' }, { id: 'CD8 T cells', label: 'CD8 T cells' }],
      sample_ids: ['sample_A', 'sample_B'],
      estimates: [
        { sample_id: 'sample_A', cell_type_id: 'B cells', value: 0.7 },
        { sample_id: 'sample_A', cell_type_id: 'CD8 T cells', value: 0.3 },
        { sample_id: 'sample_B', cell_type_id: 'B cells', value: 0.4 },
        { sample_id: 'sample_B', cell_type_id: 'CD8 T cells', value: 0.6 },
      ],
      composition_summaries: [
        { sample_id: 'sample_A', reported_sum: 1, residual_fraction: 0, within_tolerance: true },
        { sample_id: 'sample_B', reported_sum: 1, residual_fraction: 0, within_tolerance: true },
      ],
      warnings: ['Imported external CIBERSORTx result.'],
      software: {
        language: 'external service', language_version: 'CIBERSORTx-2026-05',
        packages: { CIBERSORTx: 'CIBERSORTx-2026-05' },
      },
      provenance: {
        expression_bundle_sha256: 'a'.repeat(64), analysis_request_sha256: 'b'.repeat(64),
        reference_sha256: 'd'.repeat(64), external_source_sha256: 'e'.repeat(64),
      },
      external_import: externalImport,
    }
    const artifact = {
      id: 'cibersortx-source', run_id: run.id, artifact_type: 'cibersortx_source',
      title: 'Original CIBERSORTx export', relative_path: 'cibersortx_source.tsv',
      mime_type: 'text/tab-separated-values', size_bytes: 512, sha256: 'e'.repeat(64),
      display_order: 3, metadata_json: { external_import: true },
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith(`/analyses/${analysis.id}/runs`)) return jsonResponse([run])
      if (url.endsWith(`/analyses/${analysis.id}`)) return jsonResponse(analysis)
      if (url.endsWith(`/runs/${run.id}/deconvolution-results`)) return jsonResponse(result)
      if (url.endsWith(`/runs/${run.id}/result-manifest`)) {
        return jsonResponse({ schema_version: '1.0.0', analysis_type: 'deconvolution', title: 'CIBERSORTx', summary_metrics: [], sections: [], downloads: [], warnings: [] })
      }
      if (url.endsWith(`/runs/${run.id}/artifacts`)) return jsonResponse([artifact])
      if (url.endsWith('/prepared-datasets/prepared-1/deconvolution/comparison')) {
        return jsonResponse({
          schema_version: '1.0.0', prepared_dataset_id: 'prepared-1',
          latest_successful_run_count: 1, sections: [], exclusions: [],
          interpretation: 'Only compatible results are grouped.',
        })
      }
      if (url.endsWith('/prepared-datasets/prepared-1')) {
        return jsonResponse({
          id: 'prepared-1', dataset_id: 'dataset-1', version: 1,
          preparation_run_id: 'preparation-run-1', value_types_available: ['tpm'],
          sample_count: 2, feature_count: 18000, qc_status: 'PASS',
          created_at: '2026-07-18T00:00:00Z',
        })
      }
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp(`/analyses/${analysis.id}`)

    expect(await screen.findByRole('heading', { name: 'Imported relative cell fractions' })).toBeInTheDocument()
    expect(screen.getByText('External import')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'External execution provenance' })).toBeInTheDocument()
    expect(screen.getByText(/stanford-job-123/)).toBeInTheDocument()
    expect(screen.getByText(/TranscriptForge did not receive credentials/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Original CIBERSORTx export/ })).toHaveAttribute(
      'href', expect.stringContaining('/artifacts/cibersortx-source/download'),
    )
    expect(screen.queryByRole('button', { name: 'Runner unavailable' })).not.toBeInTheDocument()
  })

  it('renders completed MCP-counter scores without fraction semantics', async () => {
    const method = {
      ...deconvolutionCapabilities.methods[1].method,
      id: 'mcp_counter', display_name: 'MCP-counter', result_type: 'enrichment_score',
      quantity_label: 'Cell-population abundance score', unit: 'arbitrary_score',
      composition_constraint: 'not_compositional', within_sample_cell_type_comparison: false,
      input: {
        ...deconvolutionCapabilities.methods[1].method.input,
        assay_options: [{ name: 'log_expression', scales: ['log2'], value_types: ['continuous'] }],
        negative_values_permitted: true,
      },
      references: [{ id: 'MCPcounter_v1', label: 'MCP-counter transcriptomic markers' }],
      default_reference: 'MCPcounter_v1',
      interpretation: 'Scores compare a population between samples and are not fractions.',
    }
    const analysis = {
      id: 'mcp-analysis-1', project_id: 'project-1', prepared_dataset_id: 'prepared-1',
      analysis_type: 'deconvolution', name: 'MCP-counter cell enrichment', description: null,
      configuration_json: {
        analysis_type: 'deconvolution', method: 'mcp_counter', assay: 'log_expression',
        parameters: { reference_profile: 'MCPcounter_v1', minimum_gene_overlap: 0.5, tumor_mode: false, scale_mrna: true },
        random_seed: 0, method_registry_version: '2026.07.2',
        method_registry_sha256: 'f'.repeat(64), method_spec: method,
        input_assay_descriptor: {
          name: 'log_expression', scale: 'log2', value_type: 'continuous',
          feature_level: 'gene', sha256: 'c'.repeat(64),
        },
        result_type: 'enrichment_score', execution_available: true,
      },
      created_at: '2026-07-18T00:00:00Z',
    }
    const run = {
      ...completedRun, id: 'mcp-run-1', run_type: 'analysis',
      prepared_dataset_id: 'prepared-1', analysis_id: analysis.id,
    }
    const result = {
      schema_version: '1.0.0', analysis_id: analysis.id, prepared_dataset_id: 'prepared-1',
      method: 'mcp_counter', method_registry_version: '2026.07.2', method_registry_sha256: 'f'.repeat(64),
      result_type: 'enrichment_score', quantity_label: 'Cell-population abundance score',
      unit: 'arbitrary_score', composition_constraint: 'not_compositional',
      input_validation: {
        assay: 'log_expression', scale: 'log2', value_type: 'continuous', feature_level: 'gene',
        identifier_namespace: 'gene_symbol', input_feature_count: 20000, mapped_feature_count: 19800,
        blank_symbol_count: 200, duplicate_symbol_count: 0, reference_gene_count: 111,
        overlap_gene_count: 108, overlap_fraction: 108 / 111, minimum_overlap_fraction: 0.5, passed: true,
      },
      reference: { id: 'MCPcounter_v1', version: 'MCPcounter-1.2.0-b6eac73', sha256: 'd'.repeat(64), cell_type_count: 2 },
      cell_types: [{ id: 'B lineage', label: 'B lineage' }, { id: 'Fibroblasts', label: 'Fibroblasts' }],
      sample_ids: ['control_1', 'treated_1'],
      estimates: [
        { sample_id: 'control_1', cell_type_id: 'B lineage', value: -0.25 },
        { sample_id: 'control_1', cell_type_id: 'Fibroblasts', value: 1.5 },
        { sample_id: 'treated_1', cell_type_id: 'B lineage', value: 2.75 },
        { sample_id: 'treated_1', cell_type_id: 'Fibroblasts', value: 0.5 },
      ],
      warnings: ['Scores are not percentages.'],
      software: { language: 'R', language_version: '4.5.0', packages: { MCPcounter: '1.2.0' } },
      provenance: {
        expression_bundle_sha256: 'a'.repeat(64), analysis_request_sha256: 'b'.repeat(64),
        reference_sha256: 'd'.repeat(64),
      },
    }
    const artifact = {
      id: 'enrichment-plot', run_id: run.id, artifact_type: 'deconvolution_enrichment_svg',
      title: 'Cell-population enrichment patterns (SVG)', relative_path: 'enrichment_scores.svg',
      mime_type: 'image/svg+xml', size_bytes: 123, sha256: 'e'.repeat(64),
      display_order: 4, metadata_json: {},
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith(`/analyses/${analysis.id}/runs`)) return jsonResponse([run])
      if (url.endsWith(`/analyses/${analysis.id}`)) return jsonResponse(analysis)
      if (url.endsWith(`/runs/${run.id}/deconvolution-results`)) return jsonResponse(result)
      if (url.endsWith(`/runs/${run.id}/result-manifest`)) {
        return jsonResponse({ schema_version: '1.0.0', analysis_type: 'deconvolution', title: 'MCP-counter', summary_metrics: [], sections: [], downloads: [], warnings: [] })
      }
      if (url.endsWith(`/runs/${run.id}/artifacts`)) return jsonResponse([artifact])
      if (url.endsWith('/prepared-datasets/prepared-1/deconvolution/comparison')) {
        const comparisonRun = (overrides: Record<string, unknown>) => ({
          analysis_id: analysis.id, analysis_name: analysis.name, run_id: run.id,
          method: 'mcp_counter', display_name: 'MCP-counter',
          result_type: 'enrichment_score', quantity_label: 'Cell-population abundance score',
          unit: 'arbitrary_score', composition_constraint: 'not_compositional',
          assay: {
            name: 'log_expression', scale: 'log2', value_type: 'continuous',
            feature_level: 'gene', identifier_namespace: 'gene_symbol',
          },
          reference: { id: 'MCPcounter_v1', version: 'MCPcounter-1.2.0-b6eac73', sha256: 'd'.repeat(64) },
          reference_overlap_fraction: 108 / 111,
          sample_ids: ['control_1', 'treated_1', 'treated_2'],
          cell_types: [{ id: 'Fibroblasts', label: 'Fibroblasts' }],
          estimates: [], result_sha256: 'e'.repeat(64), method_registry_version: '2026.07.2',
          method_registry_sha256: 'f'.repeat(64), ...overrides,
        })
        return jsonResponse({
          schema_version: '1.0.0', prepared_dataset_id: 'prepared-1',
          latest_successful_run_count: 2,
          sections: [{
            id: 'enrichment-score-log-expression', result_type: 'enrichment_score',
            unit: 'arbitrary_score', composition_constraints: ['not_compositional'],
            comparison_mode: 'within_population_pattern',
            assay: {
              name: 'log_expression', scale: 'log2', value_type: 'continuous',
              feature_level: 'gene', identifier_namespace: 'gene_symbol',
            },
            sample_ids: ['control_1', 'treated_1', 'treated_2'],
            shared_cell_types: [{ id: 'Fibroblasts', label: 'Fibroblasts' }],
            reference_mode: 'method_specific_exact_population_intersection',
            runs: [
              comparisonRun({}),
              comparisonRun({
                analysis_id: 'xcell-analysis-1', analysis_name: 'xCell enrichment',
                run_id: 'xcell-run-1', method: 'xcell', display_name: 'xCell',
                reference: { id: 'xCell64', version: 'xCell-1.1.0-a6f61a4', sha256: 'a'.repeat(64) },
              }),
            ],
            correlations: [{
              left_run_id: run.id, right_run_id: 'xcell-run-1',
              left_method: 'mcp_counter', right_method: 'xcell',
              cell_type_id: 'Fibroblasts', cell_type_label: 'Fibroblasts',
              sample_count: 3, pearson_correlation: 1,
            }],
            warnings: [
              'References remain method-specific; only exact shared population labels are compared.',
            ],
          }],
          exclusions: [],
          interpretation: 'Enrichment methods are compared only as within-population patterns across the same samples.',
        })
      }
      if (url.endsWith('/prepared-datasets/prepared-1')) {
        return jsonResponse({
          id: 'prepared-1', dataset_id: 'dataset-1', version: 1,
          preparation_run_id: 'preparation-run-1', value_types_available: ['log_expression'],
          sample_count: 2, feature_count: 20000, qc_status: 'PASS', created_at: '2026-07-18T00:00:00Z',
        })
      }
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp(`/analyses/${analysis.id}`)

    expect(await screen.findByRole('heading', { name: 'Cell-population enrichment patterns' })).toBeInTheDocument()
    expect(screen.getByText(/scores are not percentages and do not sum to one/i)).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'mcp_counter enrichment scores' })).toBeInTheDocument()
    expect(screen.getAllByText('-0.2500')).toHaveLength(2)
    expect(screen.getByText(/MCPcounter 1.2.0/)).toBeInTheDocument()
    expect(screen.queryByText('Estimated cell fractions')).not.toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Cross-method comparison' })).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'enrichment_score cross-method concordance' })).toBeInTheDocument()
    expect(screen.getByText('mcp_counter ↔ xcell')).toBeInTheDocument()
    expect(screen.getByText('1.000')).toBeInTheDocument()
    expect(screen.getByText(/references remain method-specific/i)).toBeInTheDocument()
  })

  it('renders microarray-specific QC without count-library assumptions', async () => {
    const microarrayDataset = {
      ...dataset,
      name: 'Cartilage Human Gene arrays',
      modality: 'microarray',
      source_kind: 'affymetrix_cel',
      annotation_release: 'hugene10sttranscriptcluster.db',
      status: 'prepared',
    }
    const plotArtifact = (artifactType: string, title: string) => ({
      id: artifactType, run_id: 'microarray-run-1', artifact_type: artifactType, title,
      relative_path: `rma/plots/${artifactType}.svg`, mime_type: 'image/svg+xml',
      size_bytes: 1024, sha256: 'a'.repeat(64), display_order: 1, metadata_json: {},
    })
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith('/health')) return jsonResponse(health)
      if (url.endsWith('/prepared-datasets/prepared-microarray')) {
        return jsonResponse({
          id: 'prepared-microarray', dataset_id: 'dataset-1', version: 1,
          preparation_run_id: 'microarray-run-1',
          value_types_available: ['log_expression', 'probe_expression'],
          sample_count: 8, feature_count: 23702, qc_status: 'PASS',
          created_at: '2026-07-16T00:00:00Z',
        })
      }
      if (url.endsWith('/datasets/dataset-1')) return jsonResponse(microarrayDataset)
      if (url.endsWith('/runs/microarray-run-1/qc-summary')) {
        return jsonResponse({
          schema_version: '1.0.0', status: 'PASS', sample_count: 8,
          probe_count: 257430, gene_count: 23702, reviewed_sample_count: 0,
          plots: ['plots/pca.svg'],
        })
      }
      if (url.endsWith('/runs/microarray-run-1/feature-mapping-summary')) {
        return jsonResponse({
          prepared_dataset_id: 'prepared-microarray', prepared_version: 1,
          sample_count: 8, feature_count: 23702,
          value_types_available: ['log_expression', 'probe_expression'], qc_status: 'PASS',
          mapped_feature_count: 23702, unmapped_feature_count: 0,
          duplicate_group_count: 0, mapping_coverage: 1,
          probe_count: 257430, gene_count: 23702, aggregation_method: 'highest_mad',
          probe_mapping_path: 'mappings/probe_mapping.tsv',
        })
      }
      if (url.endsWith('/runs/microarray-run-1/artifacts')) {
        return jsonResponse([
          plotArtifact('microarray_raw_boxplot', 'Raw array intensity distributions'),
          plotArtifact('microarray_pca', 'Microarray PCA'),
        ])
      }
      if (url.endsWith('/prepared-datasets/prepared-microarray/analyses')) {
        return jsonResponse([{
          id: 'analysis-microarray-de', project_id: 'project-1',
          prepared_dataset_id: 'prepared-microarray', analysis_type: 'differential_expression',
          name: 'Superficial versus deep', description: null, configuration_json: {},
          created_at: '2026-07-16T00:00:00Z',
        }])
      }
      if (url.endsWith('/prepared-datasets/prepared-microarray/differential-expression/design-options')) {
        return jsonResponse({
          sample_count: 8,
          assays: ['log_expression'],
          variables: [
            {
              name: 'cel_file', kind: 'categorical',
              levels: Array.from({ length: 8 }, (_, index) => `GSM${index + 1}.CEL.gz`),
              missing_count: 0, unique_count: 8,
            },
            {
              name: 'donor', kind: 'numeric', levels: [],
              missing_count: 0, unique_count: 4,
            },
            {
              name: 'zone', kind: 'categorical', levels: ['deep', 'superficial'],
              missing_count: 0, unique_count: 2,
            },
          ],
        })
      }
      if (url.endsWith('/prepared-datasets/prepared-microarray/differential-expression/validate-design')) {
        return jsonResponse({
          valid: true,
          formula: '~ donor + zone',
          resolved_method: 'limma',
          contrast_label: 'superficial versus deep within zone',
          sample_count: 8,
          contrast_counts: { superficial: 4, deep: 4 },
          design_matrix_columns: [
            'Intercept', 'donor[72]', 'donor[73]', 'donor[74]', 'zone[superficial]',
          ],
          design_matrix_rank: 5,
          design_cells: [],
          errors: [],
          warnings: [],
        })
      }
      return jsonResponse({ detail: 'Not found' }, 404)
    })

    renderApp('/prepared-datasets/prepared-microarray')

    expect(await screen.findByRole('heading', { name: 'Array QC' })).toBeInTheDocument()
    expect(screen.getByText('257,430 probe sets')).toBeInTheDocument()
    expect(screen.getByText('23,702 genes')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Raw array intensity distributions' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Microarray PCA' })).toBeInTheDocument()
    expect(screen.getByText('257,430 probe sets retained')).toBeInTheDocument()
    expect(screen.getByText('Aggregation: highest mad')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Saved analyses' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Superficial versus deep.*Open analysis/i }))
      .toHaveAttribute('href', '/analyses/analysis-microarray-de')
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: 'Primary variable' })).toHaveTextContent('zone')
      expect(screen.getByRole('combobox', { name: 'Numerator' })).toHaveTextContent('superficial')
      expect(screen.getByRole('combobox', { name: 'Denominator' })).toHaveTextContent('deep')
      expect(screen.getByRole('combobox', { name: 'Subject / block' })).toHaveTextContent('donor')
    })
    expect(await screen.findByText('~ donor + zone')).toBeInTheDocument()
    expect(screen.getByText('Design valid')).toBeInTheDocument()
    expect(screen.getByText('Rank 5/5')).toBeInTheDocument()
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
    fireEvent.click(screen.getByRole('checkbox', { name: 'Run optional gene-set enrichment' }))
    expect(await screen.findByText(/not a curated biological pathway database/i)).toBeInTheDocument()
    const saveButton = screen.getByRole('button', { name: 'Save design & continue to run' })
    await waitFor(() => expect(saveButton).toBeEnabled())
    fireEvent.click(saveButton)

    expect(await screen.findByRole('button', { name: 'Run differential expression' }))
      .toBeInTheDocument()
    expect(screen.getByText(/Design saved.*start the workflow/i)).toBeInTheDocument()

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
          enrichment: {
            enabled: true,
            collection_id: 'transcriptforge_demo_effects',
            permutation_count: 250,
          },
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
          enrichment: {
            enabled: true, collection_id: 'transcriptforge_demo_effects',
            ranking_metric: 'signed_log10_p_value', permutation_count: 250,
            minimum_gene_set_size: 10, maximum_gene_set_size: 500,
          },
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
      if (url.endsWith('/runs/limma-run-1/enrichment-summary')) {
        const rankedResult = {
          gene_set_id: 'TF_DEMO_TREATMENT_UP',
          gene_set_name: 'Synthetic treatment-up controls', direction: 'up',
          set_size: 150, overlap_size: 31, enrichment_score: 0.82,
          normalized_enrichment_score: 2.1, odds_ratio: null,
          p_value: 0.004, adjusted_p_value: 0.028,
          leading_edge: ['gene_up'], significant: true,
        }
        return jsonResponse({
          schema_version: '1.0.0', analysis_id: 'analysis-limma',
          collection: {
            collection_id: 'transcriptforge_demo_effects',
            name: 'TranscriptForge simulated-effect controls', version: '1.0.0',
            identifier_namespace: 'transcriptforge_demo_feature_id',
            source: 'TranscriptForge bundled deterministic demo experiment',
            license: 'PolyForm-Noncommercial-1.0.0',
            gmt_sha256: 'b'.repeat(64), set_count: 7,
          },
          source_result: {
            method: 'limma', contrast: 'stimulated versus vehicle within treatment',
            result_sha256: 'a'.repeat(64), tested_feature_count: 2,
            significant_feature_count: 1,
          },
          parameters: {
            identifier_field: 'feature_id', ranking_metric: 'signed_log10_p_value',
            random_seed: 20260716,
            permutation_count: 250, minimum_gene_set_size: 10,
            maximum_gene_set_size: 500, fdr_threshold: 0.05,
            absolute_log2_fold_change: 1,
          },
          ranked_list: [rankedResult],
          over_representation: [{
            ...rankedResult, enrichment_score: null, normalized_enrichment_score: null,
            odds_ratio: 4.2,
          }],
          warnings: [
            'This collection contains synthetic demonstration controls, not curated biological pathways.',
          ],
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
    expect(await screen.findByRole('heading', { name: 'Gene-set enrichment' })).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Ranked-list enrichment' })).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Over-representation analysis' })).toBeInTheDocument()
    expect(screen.getAllByText('TF_DEMO_TREATMENT_UP')).toHaveLength(2)
    expect(screen.getByText(/not curated biological pathways/i)).toBeInTheDocument()
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
