import ArrowForwardRoundedIcon from '@mui/icons-material/ArrowForwardRounded'
import {
  Alert,
  Button,
  Checkbox,
  Chip,
  Divider,
  FormControlLabel,
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
  importCibersortxResult,
  type DeconvolutionMethod,
} from '../api/client'
import { ErrorState, LoadingState } from './ApiState'

export function DeconvolutionSetupPanel({ preparedDatasetId }: { preparedDatasetId: string }) {
  const navigate = useNavigate()
  const [methodId, setMethodId] = useState<DeconvolutionMethod>('quantiseq')
  const [assay, setAssay] = useState('')
  const [referenceProfile, setReferenceProfile] = useState('')
  const [minimumGeneOverlap, setMinimumGeneOverlap] = useState(0.5)
  const [tumorMode, setTumorMode] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importAssay, setImportAssay] = useState('')
  const [importName, setImportName] = useState('CIBERSORTx relative fractions')
  const [signatureName, setSignatureName] = useState('LM22')
  const [signatureVersion, setSignatureVersion] = useState('')
  const [signatureSha256, setSignatureSha256] = useState('')
  const [signatureGeneCount, setSignatureGeneCount] = useState(547)
  const [mixtureGeneCount, setMixtureGeneCount] = useState(0)
  const [overlapGeneCount, setOverlapGeneCount] = useState(0)
  const [runtimeVersion, setRuntimeVersion] = useState('')
  const [externalRunId, setExternalRunId] = useState('')
  const [executedAt, setExecutedAt] = useState('')
  const [batchCorrection, setBatchCorrection] = useState<'none' | 'B-mode' | 'S-mode'>('none')
  const [permutations, setPermutations] = useState(0)
  const [fractionsDeclared, setFractionsDeclared] = useState(false)
  const capabilities = useQuery({
    queryKey: ['deconvolution-methods', preparedDatasetId],
    queryFn: ({ signal }) => fetchDeconvolutionCapabilities(preparedDatasetId, signal),
    enabled: Boolean(preparedDatasetId),
  })
  const selected = useMemo(
    () => capabilities.data?.methods.find(
      (item) => item.method.id === methodId && item.method.execution_mode === 'native',
    ),
    [capabilities.data?.methods, methodId],
  )
  const cibersortx = capabilities.data?.methods.find(
    (item) => item.method.id === 'cibersortx_external',
  )
  useEffect(() => {
    if (!capabilities.data) return
    const current = capabilities.data.methods.find(
      (item) => item.method.id === methodId && item.method.execution_mode === 'native',
    )
    const runnable = capabilities.data.methods.find(
      (item) => item.method.execution_mode === 'native' && item.execution_available,
    )
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
  useEffect(() => {
    if (cibersortx && !cibersortx.compatible_assays.includes(importAssay)) {
      setImportAssay(cibersortx.compatible_assays[0] ?? '')
    }
  }, [cibersortx, importAssay])
  const save = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error('Select a compatible deconvolution method.')
      return createDeconvolutionAnalysis(preparedDatasetId, {
        name: `${selected.method.display_name} ${selected.method.result_type === 'cell_fraction'
          ? 'cell composition'
          : 'cell enrichment'}`,
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
  const importResult = useMutation({
    mutationFn: () => {
      if (!importFile) throw new Error('Choose a CIBERSORTx result export.')
      if (!executedAt) throw new Error('Record when the external CIBERSORTx run completed.')
      return importCibersortxResult(preparedDatasetId, {
        analysis_name: importName,
        assay: importAssay,
        mode: 'relative',
        fractions_declared: true,
        batch_correction: batchCorrection,
        permutations,
        mixture_gene_count: mixtureGeneCount,
        overlap_gene_count: overlapGeneCount,
        signature: {
          name: signatureName,
          version: signatureVersion,
          sha256: signatureSha256,
          gene_count: signatureGeneCount,
        },
        runtime: {
          version: runtimeVersion,
          external_run_id: externalRunId,
          executed_at: new Date(executedAt).toISOString(),
        },
      }, importFile)
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
                {capabilities.data.methods
                  .filter((item) => item.method.execution_mode === 'native')
                  .map((item) => (
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
                {(selected?.compatible_assays ?? []).map((name) => (
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
                {(selected?.method.references ?? []).map((reference) => (
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
            <Divider />
            <Stack spacing={2}>
              <div>
                <Typography variant="overline" color="secondary.main" fontWeight={750}>
                  External result
                </Typography>
                <Typography variant="h6" fontWeight={700}>
                  Import CIBERSORTx relative fractions
                </Typography>
                <Typography variant="body2" color="text.secondary" mt={0.5}>
                  TranscriptForge does not run CIBERSORTx or handle its credentials. Importing
                  requires exact source, signature, input-assay, overlap, and external-runtime
                  provenance.
                </Typography>
              </div>
              {!cibersortx?.configuration_available && (
                <Alert severity="info">
                  This Expression Bundle does not contain the compatible linear nonnegative TPM
                  assay required to link an external CIBERSORTx result.
                </Alert>
              )}
              {cibersortx?.configuration_available && (
                <>
                  <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
                    <TextField
                      label="Analysis name"
                      size="small"
                      value={importName}
                      onChange={(event) => setImportName(event.target.value)}
                      sx={{ flex: 1 }}
                    />
                    <TextField
                      select
                      label="CIBERSORTx input assay"
                      size="small"
                      value={importAssay}
                      onChange={(event) => setImportAssay(event.target.value)}
                      sx={{ minWidth: 210 }}
                    >
                      {cibersortx.compatible_assays.map((name) => (
                        <MenuItem key={name} value={name}>{name}</MenuItem>
                      ))}
                    </TextField>
                    <Button variant="outlined" component="label">
                      {importFile ? importFile.name : 'Choose result table'}
                      <input
                        hidden
                        type="file"
                        accept=".txt,.tsv,.csv,text/plain,text/tab-separated-values,text/csv"
                        onChange={(event) => setImportFile(event.target.files?.[0] ?? null)}
                      />
                    </Button>
                  </Stack>
                  <Typography variant="subtitle2">Signature matrix provenance</Typography>
                  <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
                    <TextField label="Signature name" size="small" value={signatureName} onChange={(event) => setSignatureName(event.target.value)} />
                    <TextField label="Signature version" size="small" value={signatureVersion} onChange={(event) => setSignatureVersion(event.target.value)} />
                    <TextField label="Signature SHA-256" size="small" value={signatureSha256} onChange={(event) => setSignatureSha256(event.target.value.trim().toLowerCase())} sx={{ flex: 1 }} />
                    <TextField label="Signature genes" type="number" size="small" value={signatureGeneCount} onChange={(event) => setSignatureGeneCount(Number(event.target.value))} sx={{ width: 150 }} />
                  </Stack>
                  <Typography variant="subtitle2">External execution provenance</Typography>
                  <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
                    <TextField label="CIBERSORTx version" size="small" value={runtimeVersion} onChange={(event) => setRuntimeVersion(event.target.value)} />
                    <TextField label="External run ID" size="small" value={externalRunId} onChange={(event) => setExternalRunId(event.target.value)} />
                    <TextField label="Executed at" type="datetime-local" size="small" value={executedAt} onChange={(event) => setExecutedAt(event.target.value)} InputLabelProps={{ shrink: true }} />
                    <TextField select label="Batch correction" size="small" value={batchCorrection} onChange={(event) => setBatchCorrection(event.target.value as 'none' | 'B-mode' | 'S-mode')} sx={{ minWidth: 170 }}>
                      <MenuItem value="none">None</MenuItem>
                      <MenuItem value="B-mode">B-mode</MenuItem>
                      <MenuItem value="S-mode">S-mode</MenuItem>
                    </TextField>
                    <TextField label="Permutations" type="number" size="small" value={permutations} onChange={(event) => setPermutations(Number(event.target.value))} sx={{ width: 145 }} />
                  </Stack>
                  <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
                    <TextField label="Mixture genes" type="number" size="small" value={mixtureGeneCount} onChange={(event) => setMixtureGeneCount(Number(event.target.value))} />
                    <TextField label="Overlapping signature genes" type="number" size="small" value={overlapGeneCount} onChange={(event) => setOverlapGeneCount(Number(event.target.value))} />
                  </Stack>
                  <FormControlLabel
                    control={<Checkbox checked={fractionsDeclared} onChange={(event) => setFractionsDeclared(event.target.checked)} />}
                    label="I declare that this is a CIBERSORTx relative-mode export and its cell-population values are relative fractions."
                  />
                  <Button
                    variant="contained"
                    onClick={() => importResult.mutate()}
                    disabled={
                      importResult.isPending
                      || !importFile
                      || !importName.trim()
                      || !signatureName.trim()
                      || !signatureVersion.trim()
                      || !/^[a-f0-9]{64}$/.test(signatureSha256)
                      || signatureGeneCount < 1
                      || mixtureGeneCount < 1
                      || overlapGeneCount < 1
                      || overlapGeneCount > signatureGeneCount
                      || overlapGeneCount > mixtureGeneCount
                      || !runtimeVersion.trim()
                      || !externalRunId.trim()
                      || !executedAt
                      || permutations < 0
                      || !fractionsDeclared
                    }
                    sx={{ width: { xs: '100%', sm: 'fit-content' } }}
                  >
                    {importResult.isPending ? 'Validating import…' : 'Validate and import result'}
                  </Button>
                  {importResult.isError && <Alert severity="error">{importResult.error.message}</Alert>}
                </>
              )}
            </Stack>
          </>
        )}
      </Stack>
    </Paper>
  )
}
