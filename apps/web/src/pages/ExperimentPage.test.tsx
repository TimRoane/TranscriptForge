import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { App } from '../App'
import type { DevelopmentExperiment, Recommendation } from '../api/client'

const now = '2026-07-18T12:00:00Z'
const assignments = ['bio1_100', 'bio1_25', 'bio2_100', 'bio2_25'].map((measurement, index) => ({
  measurement_id: measurement,
  biological_sample_id: measurement.slice(0, 4),
  prepared_dataset_id: 'prepared-1',
  include: true,
  exclusion_reason: null,
  replicate_id: null,
  pair_id: measurement.slice(0, 4),
  input_ng: measurement.endsWith('100') ? 100 : 25,
  dv200: measurement.endsWith('100') ? 70 : 45,
  sequencing_run: index % 2 ? 'run-b' : 'run-a',
  condition: null, run: null, quality_metric: null,
  operator: 'operator-1', reagent_lot: 'lot-1', instrument: 'instrument-1', processing_order: index + 1,
  extraction_method: null, library_method: null, sequencing_depth: null,
  specimen_group: null, technical_failure: false,
}))
const experiment: DevelopmentExperiment = {
  id: 'experiment-1', assay_project_id: 'assay-1', question_id: 'question-1',
  prepared_dataset_id: 'prepared-1', parent_experiment_id: null, name: 'FFPE input exploration',
  experiment_type: 'INPUT_DEGRADATION_EXPLORATION', objective: 'Explore paired stability.',
  mode: 'ANALYZE_EXISTING', status: 'DESIGN_VALID',
  experiment_spec: { analysis_plan: { reference_level: 100 } },
  experiment_spec_uri: null, experiment_spec_sha256: null, assignments,
  assignments_uri: null, assignments_sha256: null,
  design_validation: {
    schema_version: '1.0.0', valid: true, retrospective_mapping: true,
    measurement_count: 4, biological_sample_count: 2, included_measurement_count: 4,
    reference_level: 100, input_levels: [100, 25],
    findings: [{ severity: 'WARNING', code: 'DESIGN.RETROSPECTIVE_MAPPING', message: 'Assignments were mapped after measurements existed.', facts: { mode: 'ANALYZE_EXISTING' }, recommendation: 'Report this limitation.' }],
    errors: [], warnings: [], informational: [],
  },
  development_bundle_uri: null, current_revision: 1, created_by: 'local-user',
  created_at: now, updated_at: now, locked_at: null, completed_at: null,
}

function response(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } })
}

afterEach(() => vi.restoreAllMocks())

it('shows design evidence and makes the lock-to-run transition explicit', async () => {
  let current = experiment
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.endsWith('/health')) return response({ status: 'ok', service: 'transcriptforge-api', version: '0.1.0', environment: 'test', deployment_mode: 'single_user_local' })
    if (url.endsWith('/experiments/experiment-1/results')) return response({ experiment_id: 'experiment-1', status: current.status, run_id: null, decision_summary: null, recommendations: null, artifacts: [] })
    if (url.endsWith('/experiments/experiment-1/recommendations')) return response([])
    if (url.endsWith('/experiments/experiment-1/lock-execution-revision') && init?.method === 'POST') {
      current = { ...current, status: 'LOCKED_FOR_EXECUTION', experiment_spec_sha256: 'a'.repeat(64), locked_at: now }
      return response(current)
    }
    if (url.endsWith('/experiments/experiment-1')) return response(current)
    return response({ detail: 'Not found' }, 404)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/experiments/experiment-1']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><App /></MemoryRouter></QueryClientProvider>)

  expect(await screen.findByRole('heading', { name: 'FFPE input exploration' })).toBeInTheDocument()
  expect(screen.getByText('Assignments were mapped after measurements existed.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Lock revision and continue to run' }))
  expect(await screen.findByRole('button', { name: 'Run locked experiment' })).toBeInTheDocument()
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/lock-execution-revision'), expect.objectContaining({ method: 'POST' })))
})

it('accepts a result recommendation into an editable follow-up draft', async () => {
  const followUp = {
    ...experiment,
    id: 'experiment-2',
    parent_experiment_id: experiment.id,
    name: 'Balanced confirmation: FFPE input exploration',
    mode: 'PLAN_FIRST' as const,
  }
  const recommendation: Recommendation = {
    id: 'recommendation-1', assay_project_id: 'assay-1', source_type: 'experiment',
    source_id: experiment.id, rule_id: 'EXPERIMENT.BALANCED_CONFIRMATION',
    recommendation_type: 'FOLLOW_UP_EXPERIMENT', title: 'Run a balanced confirmation',
    summary: 'Confirm the exploratory input trend in a prospectively balanced study.',
    why: 'The current result is descriptive.', what_it_resolves: 'Confirmation evidence',
    stage: 'FEASIBILITY', priority: 1, requirement_level: 'STRONGLY_RECOMMENDED', status: 'OPEN',
    required_inputs: [], expected_output: 'A locked confirmation experiment', proposed_action: {},
    evidence_refs: [], assumptions: [], limitations: [], alternative_action_ids: [],
    scientist_decision_required: true, created_at: now, resolved_at: null,
  }
  const summary = {
    schema_version: '1.0.0', question: 'How stable is expression at lower RNA input?',
    finding: 'Profile stability declined with input.', evidence: [], limitations: ['Exploratory only.'],
    criteria_mode: 'EXPLORATORY', condition_results: [{ input_ng: 25, measurement_count: 2, mean_profile_correlation: 0.93, descriptive_stability_indicator: false }],
    recommended_next_action_ids: [recommendation.id], scientist_decision_required: true as const,
  }
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.endsWith('/health')) return response({ status: 'ok', service: 'transcriptforge-api', version: '0.1.0', environment: 'test', deployment_mode: 'single_user_local' })
    if (url.endsWith('/experiments/experiment-1/results')) return response({ experiment_id: experiment.id, status: 'SUCCEEDED', run_id: 'run-1', decision_summary: summary, recommendations: null, artifacts: [] })
    if (url.endsWith('/experiments/experiment-1/recommendations')) return response([recommendation])
    if (url.endsWith('/experiments/experiment-1/recommendations/recommendation-1/accept-follow-up') && init?.method === 'POST') return response(followUp, 201)
    if (url.endsWith('/experiments/experiment-2/results')) return response({ experiment_id: followUp.id, status: followUp.status, run_id: null, decision_summary: null, recommendations: null, artifacts: [] })
    if (url.endsWith('/experiments/experiment-2/recommendations')) return response([])
    if (url.endsWith('/experiments/experiment-2')) return response(followUp)
    if (url.endsWith('/experiments/experiment-1')) return response({ ...experiment, status: 'SUCCEEDED' })
    return response({ detail: 'Not found' }, 404)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/experiments/experiment-1']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><App /></MemoryRouter></QueryClientProvider>)

  expect(await screen.findByRole('heading', { name: 'Evidence review' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Accept' }))
  fireEvent.change(await screen.findByRole('textbox', { name: /Scientist rationale/ }), { target: { value: 'Confirm with prospective balance.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Accept and create draft' }))

  expect(await screen.findByRole('heading', { name: followUp.name })).toBeInTheDocument()
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining('/accept-follow-up'),
    expect.objectContaining({ method: 'POST' }),
  ))
})

it('renders paired multi-endpoint evidence without ranking a condition from one metric', async () => {
  const pairedAssignments = [1, 2, 3, 4].flatMap((sample) => ['method_a', 'method_b'].map((condition, index) => ({
    measurement_id: `pair_${sample}_${condition}`,
    biological_sample_id: `pair_${sample}`,
    prepared_dataset_id: 'prepared-paired',
    include: true,
    exclusion_reason: null,
    replicate_id: condition,
    pair_id: `pair_${sample}`,
    input_ng: null,
    dv200: null,
    sequencing_run: null,
    condition,
    run: `run_${1 + sample % 2}`,
    quality_metric: 40 + sample * 10,
    operator: 'operator-1', reagent_lot: 'lot-1', instrument: null,
    processing_order: (sample - 1) * 2 + index + 1,
    extraction_method: condition,
    library_method: null,
    sequencing_depth: null,
    specimen_group: null,
    technical_failure: false,
  })))
  const paired: DevelopmentExperiment = {
    ...experiment,
    id: 'paired-experiment',
    name: 'Paired library comparison',
    experiment_type: 'PAIRED_CONDITION_COMPARISON',
    status: 'SUCCEEDED',
    prepared_dataset_id: 'prepared-paired',
    experiment_spec: { analysis_plan: { reference_condition: 'method_a', comparator_condition: 'method_b' } },
    assignments: pairedAssignments,
    design_validation: {
      schema_version: '1.0.0', valid: true, retrospective_mapping: true,
      measurement_count: 8, biological_sample_count: 4, included_measurement_count: 8,
      reference_condition: 'method_a', comparator_condition: 'method_b',
      conditions: ['method_a', 'method_b'], complete_pair_count: 4,
      findings: [], errors: [], warnings: [], informational: [],
    },
  }
  const pairedSummary = {
    schema_version: '1.0.0', question: 'How do the paired methods compare?',
    finding: 'The paired difference was small with high profile concordance.',
    evidence: [{ type: 'primary_results', path: 'results/primary_results.json' }],
    limitations: ['Do not rank a condition from one metric alone.'],
    criteria_mode: 'exploratory',
    condition_results: [{
      reference_condition: 'method_a', comparator_condition: 'method_b', pair_count: 4,
      mean_paired_difference: 0.08, mean_profile_correlation: 0.998,
      failure_rate_difference: 0,
    }],
    recommended_next_action_ids: [], scientist_decision_required: true,
  }
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/health')) return response({ status: 'ok', service: 'transcriptforge-api', version: '0.1.0', environment: 'test', deployment_mode: 'single_user_local' })
    if (url.endsWith('/experiments/paired-experiment/results')) return response({ experiment_id: paired.id, status: paired.status, run_id: 'run-paired', decision_summary: pairedSummary, recommendations: null, artifacts: [] })
    if (url.endsWith('/experiments/paired-experiment/recommendations')) return response([])
    if (url.endsWith('/experiments/paired-experiment')) return response(paired)
    return response({ detail: 'Not found' }, 404)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/experiments/paired-experiment']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><App /></MemoryRouter></QueryClientProvider>)

  expect(await screen.findByRole('heading', { name: 'Paired library comparison' })).toBeInTheDocument()
  expect(screen.getByText(/4 complete pairs/)).toBeInTheDocument()
  expect(screen.getByText('method_b versus method_a')).toBeInTheDocument()
  expect(screen.getAllByText(/Do not rank a condition from one metric/)).toHaveLength(2)
})

it('renders technical-feasibility assignments and exploratory success evidence', async () => {
  const feasibility: DevelopmentExperiment = {
    ...experiment,
    id: 'feasibility-experiment',
    name: 'Usable RNA technical feasibility',
    experiment_type: 'TECHNICAL_FEASIBILITY',
    status: 'SUCCEEDED',
    experiment_spec: { analysis_plan: { criteria_mode: 'exploratory' } },
    assignments: assignments.map((row, index) => ({
      ...row,
      run: row.sequencing_run,
      specimen_group: index < 2 ? 'FFPE' : 'fresh_frozen',
      technical_failure: index === 1,
    })),
    design_validation: {
      schema_version: '1.0.0', valid: true, retrospective_mapping: true,
      measurement_count: 4, biological_sample_count: 2, included_measurement_count: 4,
      run_levels: ['run-a', 'run-b'], specimen_groups: ['FFPE', 'fresh_frozen'],
      findings: [], errors: [], warnings: [], informational: [],
    },
  }
  const summary = {
    schema_version: '1.0.0', question: 'Can usable RNA measurements be generated?',
    finding: 'Three of four measurements were technically usable.', evidence: [],
    limitations: ['Failure associations are descriptive.'], criteria_mode: 'exploratory',
    condition_results: [
      { group: 'FFPE', measurement_count: 2, successful_measurements: 1, technical_success_rate: 0.5, median_detected_genes: 20 },
      { group: 'fresh_frozen', measurement_count: 2, successful_measurements: 2, technical_success_rate: 1, median_detected_genes: 20 },
    ],
    recommended_next_action_ids: [], scientist_decision_required: true,
  }
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/health')) return response({ status: 'ok', service: 'transcriptforge-api', version: '0.1.0', environment: 'test', deployment_mode: 'single_user_local' })
    if (url.endsWith('/experiments/feasibility-experiment/results')) return response({ experiment_id: feasibility.id, status: feasibility.status, run_id: 'run-feasibility', decision_summary: summary, recommendations: null, artifacts: [] })
    if (url.endsWith('/experiments/feasibility-experiment/recommendations')) return response([])
    if (url.endsWith('/experiments/feasibility-experiment')) return response(feasibility)
    return response({ detail: 'Not found' }, 404)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/experiments/feasibility-experiment']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><App /></MemoryRouter></QueryClientProvider>)

  expect(await screen.findByRole('heading', { name: feasibility.name })).toBeInTheDocument()
  expect(screen.getByText(/2 specimen group\(s\)/)).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Technical feasibility evidence' })).toBeInTheDocument()
  expect(screen.getByText('Technical success rate: 50.0%')).toBeInTheDocument()
  expect(screen.getByText(/does not establish a clinical specimen requirement/)).toBeInTheDocument()
})

it('renders constrained multifactor evidence and model boundary', async () => {
  const multifactor: DevelopmentExperiment = {
    ...experiment,
    id: 'multifactor-experiment',
    name: 'Constrained multifactor optimization',
    experiment_type: 'MULTIFACTOR_OPTIMIZATION',
    status: 'SUCCEEDED',
    assignments: assignments.map((row, index) => ({
      ...row,
      extraction_method: index % 2 ? 'method_b' : 'method_a',
      run: row.sequencing_run,
    })),
    design_validation: {
      schema_version: '1.0.0', valid: true, retrospective_mapping: true,
      measurement_count: 4, biological_sample_count: 2, included_measurement_count: 4,
      design_matrix_rank: 4, design_matrix_columns: 4, residual_degrees_of_freedom: 8,
      findings: [], errors: [], warnings: [], informational: [],
    },
  }
  const summary = {
    schema_version: '1.0.0', question: 'Which factor combinations merit confirmation?',
    finding: 'Bounded fixed effects were estimated.', evidence: [], limitations: ['Exploratory only.'],
    criteria_mode: 'exploratory',
    condition_results: [{ extraction_method: 'method_a', input_ng: 100, measurement_count: 2, mean_expression: 5.2 }],
    recommended_next_action_ids: [], scientist_decision_required: true,
  }
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/health')) return response({ status: 'ok', service: 'transcriptforge-api', version: '0.1.0', environment: 'test', deployment_mode: 'single_user_local' })
    if (url.endsWith('/experiments/multifactor-experiment/results')) return response({ experiment_id: multifactor.id, status: multifactor.status, run_id: 'run-multifactor', decision_summary: summary, recommendations: null, artifacts: [] })
    if (url.endsWith('/experiments/multifactor-experiment/recommendations')) return response([])
    if (url.endsWith('/experiments/multifactor-experiment')) return response(multifactor)
    return response({ detail: 'Not found' }, 404)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/experiments/multifactor-experiment']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><App /></MemoryRouter></QueryClientProvider>)

  expect(await screen.findByRole('heading', { name: multifactor.name })).toBeInTheDocument()
  expect(screen.getByText(/rank 4\/4 · residual df 8/)).toBeInTheDocument()
  expect(screen.getByText(/Review effect intervals, repeated-sample variance/)).toBeInTheDocument()
})
