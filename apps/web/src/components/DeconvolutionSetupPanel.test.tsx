import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DeconvolutionSetupPanel } from './DeconvolutionSetupPanel'

const capabilities = {
  prepared_dataset_id: 'prepared-1',
  registry_version: '2026.07.3',
  registry_sha256: 'f'.repeat(64),
  methods: [
    {
      method: {
        id: 'quantiseq', display_name: 'quanTIseq', execution_mode: 'native',
        implementation_status: 'available', result_type: 'cell_fraction',
        quantity_label: 'Estimated immune-cell fraction', unit: 'fraction',
        composition_constraint: 'sum_to_one_with_other',
        within_sample_cell_type_comparison: true, between_sample_comparison: true,
        input: {
          organism: 'Homo sapiens', feature_level: 'gene', identifier_namespace: 'gene_symbol',
          assay_options: [{
            name: 'tpm', scales: ['linear'], value_types: ['nonnegative_continuous'],
          }],
          minimum_reference_overlap: 0.5, negative_values_permitted: false,
        },
        references: [{ id: 'TIL10', label: 'TIL10' }], default_reference: 'TIL10',
        interpretation: 'Cell fractions.', source_url: 'https://example.test/quantiseq',
      },
      compatible_assays: ['tpm'], configuration_available: true,
      execution_available: true, blocked_reasons: [],
    },
    {
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
        interpretation: 'External relative fractions.',
        source_url: 'https://cibersortx.stanford.edu/',
      },
      compatible_assays: ['tpm'], configuration_available: true,
      execution_available: false, blocked_reasons: ['External import only.'],
    },
  ],
}

describe('CIBERSORTx import form', () => {
  afterEach(() => vi.restoreAllMocks())

  it('submits the source file with complete relative-mode provenance', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (url.endsWith('/prepared-datasets/prepared-1/deconvolution/methods')) {
        return new Response(JSON.stringify(capabilities), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (url.endsWith('/prepared-datasets/prepared-1/deconvolution/cibersortx-imports')
        && init?.method === 'POST') {
        return new Response(JSON.stringify({ id: 'imported-analysis-1' }), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 })
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const view = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <DeconvolutionSetupPanel preparedDatasetId="prepared-1" />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByRole('heading', { name: 'Import CIBERSORTx relative fractions' })).toBeInTheDocument()
    const file = new File(
      ['Mixture\tB cells\tT cells\nsample_A\t0.7\t0.3\n'],
      'CIBERSORTx_Results.txt',
      { type: 'text/plain' },
    )
    const fileInput = view.container.querySelector<HTMLInputElement>('input[type="file"]')
    expect(fileInput).not.toBeNull()
    fireEvent.change(fileInput!, { target: { files: [file] } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Signature version' }), {
      target: { value: 'custom-2026-07' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Signature SHA-256' }), {
      target: { value: 'd'.repeat(64) },
    })
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Mixture genes' }), {
      target: { value: '18000' },
    })
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Overlapping signature genes' }), {
      target: { value: '500' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'CIBERSORTx version' }), {
      target: { value: 'CIBERSORTx-2026-05' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'External run ID' }), {
      target: { value: 'stanford-job-123' },
    })
    fireEvent.change(screen.getByLabelText('Executed at'), {
      target: { value: '2026-07-17T13:30' },
    })
    fireEvent.click(screen.getByRole('checkbox', { name: /declare that this is a CIBERSORTx relative-mode export/i }))
    const submit = screen.getByRole('button', { name: 'Validate and import result' })
    expect(submit).toBeEnabled()
    fireEvent.click(submit)

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/deconvolution/cibersortx-imports'),
      expect.objectContaining({ method: 'POST', body: expect.any(FormData) }),
    ))
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    const form = post?.[1]?.body as FormData
    const metadata = JSON.parse(String(form.get('metadata'))) as Record<string, unknown>
    expect(metadata).toMatchObject({
      assay: 'tpm', mode: 'relative', fractions_declared: true,
      mixture_gene_count: 18000, overlap_gene_count: 500,
    })
    expect(metadata.signature).toMatchObject({
      name: 'LM22', version: 'custom-2026-07', sha256: 'd'.repeat(64), gene_count: 547,
    })
    expect(form.get('file')).toBe(file)
  })
})
