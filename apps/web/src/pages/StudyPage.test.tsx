import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { App } from '../App'
import type { AnalyticalStudy, StudyResults } from '../api/client'

const now = '2026-07-18T12:00:00Z'
const assignments = ['bio_1_1', 'bio_1_2', 'bio_2_1', 'bio_2_2'].map((measurement, index) => ({
  measurement_id: measurement,
  biological_sample_id: measurement.slice(0, 5),
  replicate_id: String(index % 2 + 1),
  operator: `operator_${index % 2 + 1}`,
  run: `run_${Math.floor(index / 2) + 1}`,
  reagent_lot: `lot_${index % 2 + 1}`,
  input_level: null,
  quality_metric: null,
  qc_failure: false,
  condition: null,
  challenge_type: null,
  subgroup: null,
  instrument: 'instrument_1', day: null, site: null, include: true, exclusion_reason: null,
}))
const study: AnalyticalStudy = {
  id: 'study-1', assay_project_id: 'assay-1', question_id: 'question-1',
  model_id: 'model-locked', prepared_dataset_id: 'prepared-validation', parent_study_id: null,
  name: 'Classifier precision and reproducibility', study_type: 'PRECISION_REPRODUCIBILITY',
  objective: 'Quantify locked score stability without retraining.', status: 'DESIGN_VALID',
  study_spec_json: {}, assignments_json: assignments,
  criteria_json: [
    { key: 'score_icc', metric: 'icc', endpoint: 'classifier_score', operator: 'gte', threshold: 0.9, rationale: 'Prespecified score threshold.' },
    { key: 'call_agreement', metric: 'categorical_agreement', endpoint: 'predicted_class', operator: 'gte', threshold: 0.95, rationale: 'Prespecified call threshold.' },
  ],
  design_validation_json: {
    schema_version: '1.0.0', valid: true, included_measurement_count: 4,
    biological_sample_count: 2, replicates_per_sample: { bio_1: 2, bio_2: 2 },
    factor_levels: { operator: ['operator_1', 'operator_2'], run: ['run_1', 'run_2'] },
    design_matrix_rank: 3, design_matrix_columns: 3, errors: [], warnings: [],
  },
  study_spec_uri: null, study_spec_sha256: null, assignments_uri: null,
  assignments_sha256: null, validation_bundle_uri: null, current_revision: 1,
  created_by: 'local-user', created_at: now, updated_at: now, locked_at: null,
  completed_at: null,
}

function response(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } })
}

function renderStudy() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/studies/study-1']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><App /></MemoryRouter></QueryClientProvider>)
}

afterEach(() => vi.restoreAllMocks())

it('makes immutable lock and the subsequent run action explicit', async () => {
  let current = study
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.endsWith('/health')) return response({ status: 'ok', service: 'transcriptforge-api', version: '0.1.0', environment: 'test', deployment_mode: 'single_user_local' })
    if (url.endsWith('/studies/study-1/results')) return response({ study_id: study.id, status: current.status, run_id: null, summary: null, artifacts: [] })
    if (url.endsWith('/studies/study-1/lock') && init?.method === 'POST') {
      current = { ...current, status: 'LOCKED', study_spec_sha256: 'a'.repeat(64), assignments_sha256: 'b'.repeat(64), locked_at: now }
      return response(current)
    }
    if (url.endsWith('/studies/study-1')) return response(current)
    return response({ detail: 'Not found' }, 404)
  })
  renderStudy()

  expect(await screen.findByRole('heading', { name: study.name })).toBeInTheDocument()
  expect(screen.getByText(/applies it without feature selection/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Lock study design and continue to run' }))
  expect(await screen.findByRole('button', { name: 'Run locked validation study' })).toBeInTheDocument()
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining('/studies/study-1/lock'),
    expect.objectContaining({ method: 'POST' }),
  ))
})

it('shows individual criteria, threshold stability, and no-retraining provenance', async () => {
  const completed = { ...study, status: 'SUCCEEDED' as const, completed_at: now }
  const results: StudyResults = {
    study_id: study.id, status: 'SUCCEEDED', run_id: 'run-1',
    summary: {
      overall_status: 'PASS', finding: 'Prespecified criteria resolved to PASS.',
      limitations: ['Research-use validation evidence only.'], model_retrained: false,
      scientist_decision_required: true,
      precision: { repeatability_sd: 0.01, reproducibility_sd: 0.31 },
      variance_components: { icc: 0.97, biological_sample: 0.2 },
      agreement: { categorical_agreement: 1, per_sample_call_stability: [] },
      threshold_stability: { decision_threshold: 0.5, proximity_band: 0.1, near_threshold_count: 1, near_threshold_measurement_ids: ['bio_2_1'] },
      acceptance_results: { overall_status: 'PASS', criteria: [
        { ...study.criteria_json[0], observed: 0.97, status: 'PASS', population: 'all included measurements', uncertainty: null },
        { ...study.criteria_json[1], observed: 1, status: 'PASS', population: 'all included measurements', uncertainty: null },
      ] },
    },
    artifacts: [],
  }
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/health')) return response({ status: 'ok', service: 'transcriptforge-api', version: '0.1.0', environment: 'test', deployment_mode: 'single_user_local' })
    if (url.endsWith('/studies/study-1/results')) return response(results)
    if (url.endsWith('/studies/study-1')) return response(completed)
    return response({ detail: 'Not found' }, 404)
  })
  renderStudy()

  expect(await screen.findByRole('heading', { name: 'Precision evidence review' })).toBeInTheDocument()
  expect(screen.getByText('0.970')).toBeInTheDocument()
  expect(screen.getByText(/1 measurement\(s\) are near the boundary/)).toBeInTheDocument()
  expect(screen.getAllByText('bio_2_1').length).toBeGreaterThan(0)
  expect(screen.getByText('Execution provenance confirms model_retrained = false.')).toBeInTheDocument()
  expect(screen.getAllByText('PASS').length).toBeGreaterThan(1)
})

it('shows ordered input-limit evidence and the non-LoD interpretation boundary', async () => {
  const limitAssignments = [1, 2, 3, 4].flatMap((sample) => [100, 50, 25].map((level) => ({
    measurement_id: `limit_${sample}_${level}`,
    biological_sample_id: `limit_${sample}`,
    replicate_id: String(level),
    operator: `operator_${1 + sample % 2}`,
    run: `run_${1 + sample % 2}`,
    reagent_lot: `lot_${1 + sample % 2}`,
    input_level: level,
    quality_metric: 40 + level / 2 + sample,
    qc_failure: false,
    condition: null,
    challenge_type: null,
    subgroup: null,
    instrument: null, day: null, site: null, include: true, exclusion_reason: null,
  })))
  const limitStudy: AnalyticalStudy = {
    ...study,
    name: 'Locked endpoint input limit',
    study_type: 'INPUT_DEGRADATION_LIMIT',
    status: 'SUCCEEDED',
    assignments_json: limitAssignments,
    criteria_json: [{
      key: 'score_stability_all_levels', metric: 'mean_absolute_score_difference',
      endpoint: 'classifier_score', operator: 'all_levels', threshold: 0.1,
      rationale: 'Maximum paired score change at every lower level.',
    }],
    design_validation_json: {
      schema_version: '1.0.0', valid: true, included_measurement_count: 12,
      biological_sample_count: 4, replicates_per_sample: {},
      reference_level: 100, ordered_levels: [100, 50, 25], complete_pair_count: 4,
      factor_levels: { input_level: ['100', '50', '25'] },
      design_matrix_rank: 3, design_matrix_columns: 3, errors: [], warnings: [],
    },
  }
  const results: StudyResults = {
    study_id: study.id, status: 'SUCCEEDED', run_id: 'run-limit',
    summary: {
      overall_status: 'PASS', finding: 'All ordered-level criteria passed.',
      limitations: ['The candidate is not automatically a clinical LoD.'],
      model_retrained: false, scientist_decision_required: true,
      input_degradation: {
        levels: [
          { input_level: 100, mean_score_difference: 0, call_agreement_to_reference: 1, qc_failure_rate: 0 },
          { input_level: 50, mean_score_difference: -0.01, call_agreement_to_reference: 1, qc_failure_rate: 0 },
          { input_level: 25, mean_score_difference: -0.02, call_agreement_to_reference: 1, qc_failure_rate: 0 },
        ],
        trend: {}, change_point_exploration: {}, threshold_stability: {},
        candidate_lowest_tested_level: 25,
        candidate_interpretation: 'Lowest tested consecutive level meeting every criterion; this is not automatically a clinical LoD.',
      },
      threshold_stability: { decision_threshold: 0.5, proximity_band: 0.1, near_threshold_count: 0, near_threshold_measurement_ids: [] },
      acceptance_results: { overall_status: 'PASS', criteria: [{
        ...limitStudy.criteria_json[0], observed: { 50: 0.01, 25: 0.02 },
        status: 'PASS', population: 'all included paired measurements by ordered level',
        uncertainty: null,
      }] },
    },
    artifacts: [],
  }
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/health')) return response({ status: 'ok', service: 'transcriptforge-api', version: '0.1.0', environment: 'test', deployment_mode: 'single_user_local' })
    if (url.endsWith('/studies/study-1/results')) return response(results)
    if (url.endsWith('/studies/study-1')) return response(limitStudy)
    return response({ detail: 'Not found' }, 404)
  })
  renderStudy()

  expect(await screen.findByRole('heading', { name: 'Input/degradation limit evidence review' })).toBeInTheDocument()
  expect(screen.getByText(/Candidate lowest tested level: 25/)).toBeInTheDocument()
  expect(screen.getAllByText(/not automatically a clinical LoD/).length).toBeGreaterThan(0)
  expect(screen.getByText('Level 25')).toBeInTheDocument()
})

it('shows paired bridging evidence without treating correlation as equivalence', async () => {
  const bridgeStudy: AnalyticalStudy = {
    ...study,
    name: 'Locked endpoint paired bridge',
    study_type: 'PAIRED_BRIDGING',
    status: 'SUCCEEDED',
    criteria_json: [{
      key: 'paired_bias_margin', metric: 'paired_bias', endpoint: 'classifier_score',
      operator: 'absolute_lte', threshold: 0.05,
      rationale: 'Absolute paired bias must remain within the prespecified margin.',
    }],
  }
  const results: StudyResults = {
    study_id: study.id, status: 'SUCCEEDED', run_id: 'run-bridge',
    summary: {
      overall_status: 'PASS', finding: 'Paired equivalence criteria passed.',
      limitations: ['Research-use bridging evidence only.'],
      model_retrained: false, scientist_decision_required: true,
      paired_bridging: {
        pair_count: 6, paired_bias: 0.0042,
        paired_bias_confidence_interval_95: { lower: -0.002, upper: 0.011 },
        profile_correlation: 0.998, correlation_passes_equivalence: false,
        categorical_agreement: 1, discordance_rate: 0,
        tost_equivalence: { margin: 0.05, passed: true, method: 'confidence interval inclusion' },
        subgroup_review: [], threshold_adjacent_review: {},
      },
      threshold_stability: { decision_threshold: 0.5, proximity_band: 0.1, near_threshold_count: 0, near_threshold_measurement_ids: [] },
      acceptance_results: { overall_status: 'PASS', criteria: [{
        ...bridgeStudy.criteria_json[0], observed: 0.0042, status: 'PASS',
        population: 'all complete paired measurements', uncertainty: null,
      }] },
    },
    artifacts: [],
  }
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/health')) return response({ status: 'ok', service: 'transcriptforge-api', version: '0.1.0', environment: 'test', deployment_mode: 'single_user_local' })
    if (url.endsWith('/studies/study-1/results')) return response(results)
    if (url.endsWith('/studies/study-1')) return response(bridgeStudy)
    return response({ detail: 'Not found' }, 404)
  })
  renderStudy()

  expect(await screen.findByRole('heading', { name: 'Paired bridging evidence review' })).toBeInTheDocument()
  expect(screen.getByText(/Correlation is descriptive and cannot pass equivalence/)).toBeInTheDocument()
  expect(screen.getAllByText(/within margin/).length).toBeGreaterThan(0)
  expect(screen.getByText('0.004')).toBeInTheDocument()
})

it('shows robustness challenge evidence without a biological-specificity claim', async () => {
  const robustnessStudy: AnalyticalStudy = {
    ...study,
    name: 'Locked endpoint interference challenge',
    study_type: 'ROBUSTNESS_INTERFERENCE',
    status: 'SUCCEEDED',
    criteria_json: [{
      key: 'challenge_effect_margin', metric: 'mean_challenge_effect',
      endpoint: 'classifier_score', operator: 'absolute_lte', threshold: 0.1,
      rationale: 'The prespecified technical challenge effect must remain within margin.',
    }],
  }
  const results: StudyResults = {
    study_id: study.id, status: 'SUCCEEDED', run_id: 'run-robustness',
    summary: {
      overall_status: 'PASS', finding: 'The paired challenge effect remained within margin.',
      limitations: ['Technical challenge evidence only.'],
      model_retrained: false, scientist_decision_required: true,
      robustness_interference: {
        pair_count: 6, mean_challenge_effect: 0.018,
        challenge_effect_confidence_interval_95: { lower: 0.01, upper: 0.026 },
        maximum_effect_margin: 0.1, effect_within_margin: true,
        call_change_rate: 0, qc_failure_rate: 0,
        challenge_type_review: [], threshold_adjacent_review: {},
        biological_specificity_claims_supported: false,
      },
      threshold_stability: { decision_threshold: 0.5, proximity_band: 0.1, near_threshold_count: 0, near_threshold_measurement_ids: [] },
      acceptance_results: { overall_status: 'PASS', criteria: [{
        ...robustnessStudy.criteria_json[0], observed: 0.018, status: 'PASS',
        population: 'all complete challenge/reference pairs', uncertainty: null,
      }] },
    },
    artifacts: [],
  }
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/health')) return response({ status: 'ok', service: 'transcriptforge-api', version: '0.1.0', environment: 'test', deployment_mode: 'single_user_local' })
    if (url.endsWith('/studies/study-1/results')) return response(results)
    if (url.endsWith('/studies/study-1')) return response(robustnessStudy)
    return response({ detail: 'Not found' }, 404)
  })
  renderStudy()

  expect(await screen.findByRole('heading', { name: 'Robustness/interference evidence review' })).toBeInTheDocument()
  expect(screen.getByText(/do not establish biological specificity/)).toBeInTheDocument()
  expect(screen.getAllByText(/within margin/).length).toBeGreaterThan(0)
})
