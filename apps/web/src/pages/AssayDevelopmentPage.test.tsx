import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { App } from '../App'

const now = '2026-07-18T12:00:00Z'
const assay = {
  id: 'assay-1', project_id: 'project-1', name: 'Synthetic FFPE RNA assay',
  proposed_purpose: 'Explore a stable synthetic research classifier endpoint.',
  specimen_type: 'simulated_ffpe_tumor', biological_context: 'Synthetic tumor RNA.',
  proposed_output: 'expression_classifier_score', current_stage: 'FEASIBILITY',
  readiness_status: 'READY_FOR_RECOMMENDED_ACTION', active_question_id: 'question-1',
  assay_version: 'development-unlocked', created_by: 'local-user', created_at: now,
  updated_at: now, completed_at: null,
}
const question = {
  id: 'question-1', assay_project_id: 'assay-1',
  question_key: 'input_degradation_stability',
  plain_language_question: 'Does RNA input or degradation affect expression stability?',
  formal_question: 'Estimate paired stability across input levels.', stage: 'FEASIBILITY',
  status: 'OPEN', source: 'USER_SELECTED', created_at: now, resolved_at: null,
  resolution_summary: null,
}
const readiness = {
  schema_version: '1.0.0', stage: 'FEASIBILITY',
  status: 'READY_FOR_RECOMMENDED_ACTION', evaluated_at: now,
  ready_items: [{
    rule_id: 'GUIDANCE.QUESTION_ROUTE_READY',
    facts: { question_key: 'input_degradation_stability', prepared_expression_bundle_count: 1 },
    conclusion: 'The active question maps to a supported, constrained action.',
    severity: 'INFO', suggested_action: 'Review the routed action and its design requirements.',
    assumptions: [], documentation_url: '/docs/guided-assay-development',
  }],
  missing_items: [], blockers: [], warnings: [], recommended_action_ids: ['rec-1'],
  alternative_action_ids: [], not_recommended_action_ids: [],
}
const recommendation = {
  id: 'rec-1', assay_project_id: 'assay-1', source_type: 'READINESS',
  source_id: 'assay-1', rule_id: 'GUIDANCE.ROUTE.INPUT_DEGRADATION_STABILITY',
  recommendation_type: 'CREATE_EXPERIMENT',
  title: 'Create the recommended input/degradation experiment',
  summary: 'Use the supported template and review all generated assumptions.',
  why: 'The question and available Expression Bundle map to this design family.',
  what_it_resolves: 'The active scientific question.', stage: 'FEASIBILITY', priority: 70,
  requirement_level: 'RECOMMENDED', status: 'OPEN',
  required_inputs: ['expression_bundle', 'experiment_assignments'],
  expected_output: 'A draft configuration requiring scientist review.',
  proposed_action: { action_type: 'CREATE_EXPERIMENT', template: 'INPUT_DEGRADATION_EXPLORATION', launch_automatically: false },
  evidence_refs: [{ type: 'scientific_question', id: 'question-1' }], assumptions: [],
  limitations: ['TranscriptForge does not choose the endpoint or criteria.'],
  alternative_action_ids: [], scientist_decision_required: true, created_at: now,
  resolved_at: null,
}

function response(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } })
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/assay-development/assay-1']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => vi.restoreAllMocks())

it('renders transparent readiness and records a recommendation decision without launching', async () => {
  let resolved = false
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.endsWith('/health')) return response({ status: 'ok', service: 'transcriptforge-api', version: '0.1.0', environment: 'test', deployment_mode: 'single_user_local' })
    if (url.endsWith('/assay-projects/assay-1')) return response(assay)
    if (url.endsWith('/assay-projects/assay-1/readiness')) return response(readiness)
    if (url.endsWith('/assay-projects/assay-1/recommendations')) return response(resolved ? [] : [recommendation])
    if (url.endsWith('/assay-projects/assay-1/questions')) return response([question])
    if (url.endsWith('/assay-projects/assay-1/decisions')) return response([])
    if (url.endsWith('/assay-projects/assay-1/experiments')) return response([])
    if (url.endsWith('/assay-projects/assay-1/studies')) return response([])
    if (url.endsWith('/assay-projects/assay-1/experiment-input-options')) return response([])
    if (url.endsWith('/scientific-questions/catalog')) return response({ schema_version: '1.0.0', catalog_version: '2026.07', questions: [] })
    if (url.endsWith('/recommendations/rec-1/accept') && init?.method === 'POST') {
      resolved = true
      return response({
        decision: {
          id: 'decision-1', assay_project_id: 'assay-1', source_type: 'RECOMMENDATION',
          source_id: 'rec-1', stage: 'FEASIBILITY', decision_key: 'accepted_recommendation',
          decision: 'Accepted the recommendation.', rationale: 'The paired design matches the question.',
          selected_option: 'ACCEPTED', alternatives: [], evidence_refs: [], made_by: 'local-user',
          made_at: now, supersedes_decision_id: null,
        },
        replacement_recommendation: null,
        action_launched: false,
      })
    }
    return response({ detail: 'Not found' }, 404)
  })

  renderPage()
  expect(await screen.findByRole('heading', { name: 'Synthetic FFPE RNA assay' })).toBeInTheDocument()
  expect(
    screen.getAllByText('Does RNA input or degradation affect expression stability?').length,
  ).toBeGreaterThan(0)
  expect(screen.getByText('The active question maps to a supported, constrained action.')).toBeInTheDocument()
  expect(screen.getByText('Rule GUIDANCE.ROUTE.INPUT_DEGRADATION_STABILITY')).toBeInTheDocument()
  expect(screen.getByText('Scientist decision required')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Create recommended action' }))
  fireEvent.change(screen.getByRole('textbox', { name: 'Scientist rationale' }), {
    target: { value: 'The paired design matches the question.' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Accept and create draft' }))

  expect(await screen.findByRole('heading', { name: 'Input and degradation exploration' })).toBeInTheDocument()
  expect(screen.getByText('Recommendation accepted. The follow-up is now a visible draft; no experiment has been launched.')).toBeInTheDocument()
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining('/recommendations/rec-1/accept'),
    expect.objectContaining({ method: 'POST' }),
  ))
})
