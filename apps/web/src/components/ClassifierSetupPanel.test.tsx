import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ClassifierSetupPanel } from './ClassifierSetupPanel'

const options = {
  sample_count: 24,
  assays: ['log_expression'],
  variables: [
    {
      name: 'condition', kind: 'categorical', levels: ['control', 'treated'],
      missing_count: 0, unique_count: 2,
    },
    {
      name: 'subject_id', kind: 'categorical',
      levels: Array.from({ length: 12 }, (_, index) => `subject_${index + 1}`),
      missing_count: 0, unique_count: 12,
    },
    {
      name: 'cohort', kind: 'categorical', levels: ['site_a', 'site_b'],
      missing_count: 0, unique_count: 2,
    },
    {
      name: 'subtype', kind: 'categorical', levels: ['basal', 'immune', 'luminal'],
      missing_count: 0, unique_count: 3,
    },
  ],
}

const validation = {
  valid: true,
  method: 'elastic_net',
  assay: 'log_expression',
  outcome_column: 'condition',
  negative_class: 'control',
  positive_class: 'treated',
  class_labels: ['control', 'treated'],
  eligible_sample_count: 24,
  class_counts: { control: 12, treated: 12 },
  group_column: 'subject_id',
  group_count: 12,
  cohort_column: 'cohort',
  outer_folds: 3,
  inner_folds: 2,
  repeats: 2,
  expected_oof_prediction_count: 48,
  preprocessing_scope: 'fit_inside_each_training_fold',
  tuning_scope: 'inner_training_folds_only',
  fold_plan: [{
    repeat: 1, fold: 1, training_sample_count: 16, test_sample_count: 8,
    training_class_counts: { control: 8, treated: 8 },
    test_class_counts: { control: 4, treated: 4 },
    training_group_count: 8, test_group_count: 4, group_overlap_count: 0,
  }],
  errors: [],
  warnings: ['Internal validation only.'],
}

describe('classifier design setup', () => {
  afterEach(() => vi.restoreAllMocks())

  it('audits grouped nested CV and freezes the selected design', async () => {
    const requests: Array<{ url: string; body?: Record<string, unknown> }> = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      const body = typeof init?.body === 'string'
        ? JSON.parse(init.body) as Record<string, unknown>
        : undefined
      requests.push({ url, body })
      if (url.endsWith('/prepared-datasets/prepared-1/classifier/design-options')) {
        return new Response(JSON.stringify(options), {
          status: 200, headers: { 'Content-Type': 'application/json' },
        })
      }
      if (url.endsWith('/prepared-datasets/prepared-1/classifier/validate-design')) {
        const parameters = body?.parameters as Record<string, unknown>
        return new Response(JSON.stringify({
          ...validation,
          outer_folds: parameters.outer_folds,
          inner_folds: parameters.inner_folds,
          repeats: parameters.repeats,
          expected_oof_prediction_count: 24 * Number(parameters.repeats),
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      if (url.endsWith('/prepared-datasets/prepared-1/analyses') && init?.method === 'POST') {
        return new Response(JSON.stringify({ id: 'classifier-analysis-1' }), {
          status: 201, headers: { 'Content-Type': 'application/json' },
        })
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 })
    })
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <ClassifierSetupPanel preparedDatasetId="prepared-1" />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByRole('heading', {
      name: 'Design a leakage-resistant classifier',
    })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Design valid')).toBeInTheDocument())
    expect(screen.getByText('12 experimental units')).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Classifier outer-fold audit' })).toBeInTheDocument()
    expect(screen.getByText(/variance filtering.*standardization.*feature selection/i)).toBeInTheDocument()

    fireEvent.change(screen.getByRole('spinbutton', { name: 'Outer folds' }), {
      target: { value: '3' },
    })
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Inner folds' }), {
      target: { value: '2' },
    })
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Repeats' }), {
      target: { value: '2' },
    })
    await waitFor(() => expect(screen.getByText('48 planned OOF predictions')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Save classifier design' }))

    await waitFor(() => expect(requests.some((request) => (
      request.url.endsWith('/prepared-datasets/prepared-1/analyses')
    ))).toBe(true))
    const saved = requests.find((request) => request.url.endsWith('/analyses'))?.body
    expect(saved).toMatchObject({
      analysis_type: 'classifier', assay: 'log_expression', method: 'elastic_net',
      parameters: {
        outcome_column: 'condition', positive_class: 'treated', group_column: 'subject_id',
        cohort_column: 'cohort', validation_mode: 'repeated_nested_cross_validation',
        outer_folds: 3, inner_folds: 2, repeats: 2,
      },
    })
  })

  it('switches to a multinomial design without a binary positive class', async () => {
    const requests: Array<Record<string, unknown>> = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      const body = typeof init?.body === 'string'
        ? JSON.parse(init.body) as Record<string, unknown>
        : undefined
      if (body) requests.push(body)
      if (url.endsWith('/prepared-datasets/prepared-1/classifier/design-options')) {
        return new Response(JSON.stringify(options), {
          status: 200, headers: { 'Content-Type': 'application/json' },
        })
      }
      if (url.endsWith('/prepared-datasets/prepared-1/classifier/validate-design')) {
        return new Response(JSON.stringify({
          ...validation,
          method: 'multinomial_elastic_net',
          outcome_column: 'subtype',
          negative_class: null,
          positive_class: null,
          class_labels: ['basal', 'immune', 'luminal'],
          class_counts: { basal: 8, immune: 8, luminal: 8 },
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      if (url.endsWith('/prepared-datasets/prepared-1/analyses')) {
        return new Response(JSON.stringify({ id: 'multiclass-analysis-1' }), {
          status: 201, headers: { 'Content-Type': 'application/json' },
        })
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 })
    })
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <ClassifierSetupPanel preparedDatasetId="prepared-1" />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await screen.findByRole('combobox', { name: 'Classifier type' })
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Classifier type' }))
    fireEvent.click(screen.getByRole('option', { name: 'Multiclass elastic net' }))
    await waitFor(() => expect(screen.getByRole('combobox', {
      name: 'Multiclass outcome',
    })).toBeInTheDocument())
    expect(screen.queryByRole('combobox', { name: 'Positive class' })).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Design valid')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Save classifier design' }))

    await waitFor(() => expect(requests.some((request) => (
      request.analysis_type === 'classifier'
    ))).toBe(true))
    expect(requests.find((request) => request.analysis_type === 'classifier')).toMatchObject({
      method: 'multinomial_elastic_net',
      parameters: {
        outcome_column: 'subtype',
        positive_class: null,
        primary_metric: 'macro_roc_auc',
        probability_calibration: 'none',
        decision_threshold_strategy: 'fixed_0_5',
      },
    })
  })
})
