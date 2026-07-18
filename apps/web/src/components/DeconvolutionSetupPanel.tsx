import ArrowForwardRoundedIcon from '@mui/icons-material/ArrowForwardRounded'
import {
  Alert,
  Button,
  Chip,
  Link,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  createDeconvolutionAnalysis,
  fetchDeconvolutionCapabilities,
  type DeconvolutionMethod,
} from '../api/client'
import { ErrorState, LoadingState } from './ApiState'

export function DeconvolutionSetupPanel({ preparedDatasetId }: { preparedDatasetId: string }) {
  const navigate = useNavigate()
  const [methodId, setMethodId] = useState<DeconvolutionMethod>('epic')
  const [assay, setAssay] = useState('')
  const [referenceProfile, setReferenceProfile] = useState('')
  const [minimumGeneOverlap, setMinimumGeneOverlap] = useState(0.5)
  const [tumorMode, setTumorMode] = useState(false)
  const capabilities = useQuery({
    queryKey: ['deconvolution-methods', preparedDatasetId],
    queryFn: ({ signal }) => fetchDeconvolutionCapabilities(preparedDatasetId, signal),
    enabled: Boolean(preparedDatasetId),
  })
  const selected = useMemo(
    () => capabilities.data?.methods.find((item) => item.method.id === methodId),
    [capabilities.data?.methods, methodId],
  )
  useEffect(() => {
    if (!capabilities.data) return
    const current = capabilities.data.methods.find((item) => item.method.id === methodId)
    const runnable = capabilities.data.methods.find((item) => item.execution_available)
    if (!current?.execution_available && runnable) setMethodId(runnable.method.id as DeconvolutionMethod)
  }, [capabilities.data, methodId])
  useEffect(() => {
    if (!selected) return
    if (!selected.compatible_assays.includes(assay)) {
      setAssay(selected.compatible_assays[0] ?? '')
    }
    const references = selected.method.references.map((item) => item.id)
    if (!references.includes(referenceProfile)) {
      setReferenceProfile(selected.method.default_reference ?? references[0] ?? '')
    }
    setMinimumGeneOverlap((current) => Math.max(
      current,
      selected.method.input.minimum_reference_overlap,
    ))
  }, [assay, referenceProfile, selected])
  const save = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error('Select a compatible deconvolution method.')
      return createDeconvolutionAnalysis(preparedDatasetId, {
        name: `${selected.method.display_name} cell composition`,
        method: methodId,
        assay,
        referenceProfile,
        minimumGeneOverlap,
        tumorMode,
        scaleMrna: true,
      })
    },
    onSuccess: (analysis) => navigate(`/analyses/${analysis.id}`),
  })

  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Stack spacing={2.5}>
        <div>
          <Typography variant="overline" color="secondary.main" fontWeight={750}>
            Cell composition
          </Typography>
          <Typography variant="h5" fontWeight={700}>Configure cell-type deconvolution</Typography>
          <Typography color="text.secondary" mt={0.5}>
            Method capabilities are checked against the immutable assay scale and gene metadata.
            Fraction outputs and enrichment scores retain different result semantics.
          </Typography>
        </div>
        {capabilities.isPending && <LoadingState label="Checking deconvolution methods…" />}
        {capabilities.isError && <ErrorState error={capabilities.error} />}
        {capabilities.data && (
          <>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }}>
              <TextField
                select
                label="Deconvolution method"
                size="small"
                value={methodId}
                onChange={(event) => setMethodId(event.target.value as DeconvolutionMethod)}
                sx={{ minWidth: 220 }}
              >
                {capabilities.data.methods.map((item) => (
                  <MenuItem
                    key={item.method.id}
                    value={item.method.id}
                    disabled={!item.configuration_available}
                  >
                    {item.method.display_name} · {item.method.result_type.replace('_', ' ')}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Compatible assay"
                size="small"
                value={assay}
                onChange={(event) => setAssay(event.target.value)}
                sx={{ minWidth: 180 }}
              >
                {selected?.compatible_assays.map((name) => (
                  <MenuItem key={name} value={name}>{name}</MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Reference"
                size="small"
                value={selected?.method.references.some((item) => item.id === referenceProfile)
                  ? referenceProfile
                  : ''}
                onChange={(event) => setReferenceProfile(event.target.value)}
                sx={{ minWidth: 230 }}
              >
                {selected?.method.references.map((reference) => (
                  <MenuItem key={reference.id} value={reference.id}>{reference.label}</MenuItem>
                ))}
              </TextField>
              <TextField
                label="Minimum gene overlap"
                type="number"
                size="small"
                value={minimumGeneOverlap}
                onChange={(event) => setMinimumGeneOverlap(Number(event.target.value))}
                inputProps={{
                  min: selected?.method.input.minimum_reference_overlap ?? 0,
                  max: 1,
                  step: 0.05,
                }}
                sx={{ width: 190 }}
              />
              {methodId === 'quantiseq' && (
                <TextField
                  select
                  label="Study context"
                  size="small"
                  value={tumorMode ? 'tumor' : 'non_tumor'}
                  onChange={(event) => setTumorMode(event.target.value === 'tumor')}
                  sx={{ minWidth: 190 }}
                >
                  <MenuItem value="non_tumor">Blood / non-tumor</MenuItem>
                  <MenuItem value="tumor">Tumor tissue</MenuItem>
                </TextField>
              )}
            </Stack>
            {selected && (
              <Paper variant="outlined" sx={{ p: 2.5, bgcolor: 'background.default' }}>
                <Stack spacing={1.25}>
                  <Stack direction="row" spacing={1} flexWrap="wrap">
                    <Chip
                      color={selected.method.result_type === 'cell_fraction' ? 'primary' : 'warning'}
                      label={selected.method.result_type === 'cell_fraction'
                        ? 'Cell fractions'
                        : 'Enrichment scores · not percentages'}
                    />
                    <Chip label={`Registry ${capabilities.data.registry_version}`} variant="outlined" />
                    <Chip
                      label={selected.execution_available
                        ? 'Runner available'
                        : selected.method.implementation_status === 'license_blocked'
                          ? 'License-gated'
                          : 'Runner pending'}
                      color={selected.execution_available ? 'success' : 'default'}
                    />
                  </Stack>
                  <Typography>{selected.method.interpretation}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    Requires {selected.method.input.identifier_namespace.replace('_', ' ')} identifiers,
                    {' '}{selected.method.input.feature_level}-level input, and at least{' '}
                    {(selected.method.input.minimum_reference_overlap * 100).toFixed(0)}% reference
                    overlap. <Link href={selected.method.source_url} target="_blank" rel="noreferrer">
                      Method source
                    </Link>
                  </Typography>
                </Stack>
              </Paper>
            )}
            {selected && !selected.execution_available && (
              <Alert severity="info">
                {selected.method.implementation_status === 'license_blocked'
                  ? 'This method is not bundled because its upstream license requires separate acceptance and restricts redistribution.'
                  : 'The validation and saved-design contract are ready, but the scientific runner is not implemented yet.'}
              </Alert>
            )}
            <Button
              variant="contained"
              endIcon={<ArrowForwardRoundedIcon />}
              onClick={() => save.mutate()}
              disabled={
                !selected?.configuration_available
                || !assay
                || !referenceProfile
                || minimumGeneOverlap < (selected?.method.input.minimum_reference_overlap ?? 0)
                || minimumGeneOverlap > 1
                || save.isPending
              }
              sx={{ width: { xs: '100%', sm: 'fit-content' } }}
            >
              {save.isPending ? 'Saving design…' : 'Save deconvolution design'}
            </Button>
            {save.isError && <Alert severity="error">{save.error.message}</Alert>}
          </>
        )}
      </Stack>
    </Paper>
  )
}
