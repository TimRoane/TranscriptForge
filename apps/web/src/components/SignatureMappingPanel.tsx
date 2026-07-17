import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded'
import PlayArrowRoundedIcon from '@mui/icons-material/PlayArrowRounded'
import {
  Alert,
  Button,
  Checkbox,
  Chip,
  FormControlLabel,
  Link,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  createSignatureScoringAnalysis,
  fetchSignatureDefinitions,
  fetchSignatureMappings,
  mapSignatureDefinition,
  signatureMappingDownloadUrl,
  runAnalysis,
  type SignatureScoringMethod,
} from '../api/client'
import { ErrorState, LoadingState } from './ApiState'

export function SignatureMappingPanel({
  preparedDatasetId,
  projectId,
}: {
  preparedDatasetId: string
  projectId: string
}) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [definitionId, setDefinitionId] = useState('')
  const [scoringMethod, setScoringMethod] = useState<SignatureScoringMethod>('mean_expression')
  const [minimumGeneSetSize, setMinimumGeneSetSize] = useState(1)
  const [maximumGeneSetSize, setMaximumGeneSetSize] = useState(5000)
  const [gsvaKcdf, setGsvaKcdf] = useState<'auto' | 'Gaussian' | 'Poisson' | 'none'>('Gaussian')
  const [gsvaTau, setGsvaTau] = useState(1)
  const [gsvaMaxDiff, setGsvaMaxDiff] = useState(true)
  const [gsvaAbsRanking, setGsvaAbsRanking] = useState(false)
  const [ssgseaAlpha, setSsgseaAlpha] = useState(0.25)
  const [ssgseaNormalize, setSsgseaNormalize] = useState(true)
  const definitions = useQuery({
    queryKey: ['signature-definitions', projectId],
    queryFn: ({ signal }) => fetchSignatureDefinitions(projectId, signal),
    enabled: Boolean(projectId),
  })
  const mappings = useQuery({
    queryKey: ['signature-mappings', preparedDatasetId],
    queryFn: ({ signal }) => fetchSignatureMappings(preparedDatasetId, signal),
    enabled: Boolean(preparedDatasetId),
  })
  const mapDefinition = useMutation({
    mutationFn: () => mapSignatureDefinition(definitionId, preparedDatasetId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['signature-mappings', preparedDatasetId],
      })
    },
  })
  const scoreSignature = useMutation({
    mutationFn: async ({ mappingId, name }: { mappingId: string; name: string }) => {
      const analysis = await createSignatureScoringAnalysis(preparedDatasetId, {
        name: `${name} · ${scoringMethod.replaceAll('_', ' ')}`,
        method: scoringMethod,
        signatureMappingId: mappingId,
        parameters: {
          minimum_gene_set_size: minimumGeneSetSize,
          maximum_gene_set_size: maximumGeneSetSize,
          gsva_kcdf: gsvaKcdf,
          gsva_tau: gsvaTau,
          gsva_max_diff: gsvaMaxDiff,
          gsva_abs_ranking: gsvaAbsRanking,
          ssgsea_alpha: ssgseaAlpha,
          ssgsea_normalize: ssgseaNormalize,
        },
      })
      await runAnalysis(analysis.id)
      return analysis
    },
    onSuccess: (analysis) => navigate(`/analyses/${analysis.id}`),
  })
  const definitionNames = new Map(
    definitions.data?.map((definition) => [definition.id, definition.name]) ?? [],
  )
  const rParametersInvalid = (scoringMethod === 'gsva' || scoringMethod === 'ssgsea') && (
    !Number.isInteger(minimumGeneSetSize)
    || !Number.isInteger(maximumGeneSetSize)
    || minimumGeneSetSize < 1
    || minimumGeneSetSize > 5000
    || maximumGeneSetSize < minimumGeneSetSize
    || maximumGeneSetSize > 50000
    || (scoringMethod === 'gsva' && (
      !Number.isFinite(gsvaTau) || gsvaTau <= 0 || gsvaTau > 10
    ))
    || (scoringMethod === 'ssgsea' && (
      !Number.isFinite(ssgseaAlpha) || ssgseaAlpha <= 0 || ssgseaAlpha > 10
    ))
  )

  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Stack spacing={2.5}>
        <div>
          <Typography variant="overline" color="secondary.main" fontWeight={750}>
            Signature mapping
          </Typography>
          <Typography variant="h5" fontWeight={700}>Map signatures to this bundle</Typography>
          <Typography color="text.secondary" mt={0.5}>
            Inspect coverage, missing genes, ambiguities, and duplicate handling before any score
            can be calculated.
          </Typography>
        </div>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }}>
          <TextField
            select
            label="Signature definition"
            size="small"
            value={definitionId}
            onChange={(event) => setDefinitionId(event.target.value)}
            sx={{ minWidth: 260 }}
          >
            {definitions.data?.length === 0 && (
              <MenuItem value="" disabled>Upload a definition on the project page</MenuItem>
            )}
            {definitions.data?.map((definition) => (
              <MenuItem key={definition.id} value={definition.id}>{definition.name}</MenuItem>
            ))}
          </TextField>
          <Button
            variant="contained"
            onClick={() => mapDefinition.mutate()}
            disabled={!definitionId || mapDefinition.isPending}
          >
            {mapDefinition.isPending ? 'Mapping…' : 'Create mapping report'}
          </Button>
        </Stack>
        {definitions.isError && <ErrorState error={definitions.error} />}
        {mapDefinition.isError && <Alert severity="error">{mapDefinition.error.message}</Alert>}
        {scoreSignature.isError && <Alert severity="error">{scoreSignature.error.message}</Alert>}
        {mappings.isPending && <LoadingState label="Loading signature mappings…" />}
        {mappings.isError && <ErrorState error={mappings.error} />}
        {mappings.data?.length === 0 && (
          <Alert severity="info">
            Scoring is blocked until a mapping report has been created and reviewed.
          </Alert>
        )}
        {mappings.data?.map((mapping) => (
          <Paper key={mapping.id} variant="outlined" sx={{ p: 2.5, bgcolor: 'background.default' }}>
            <Stack spacing={1.5}>
              <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={1}>
                <div>
                  <Typography fontWeight={700}>
                    {definitionNames.get(mapping.signature_definition_id) ?? 'Signature definition'}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Mapping coverage: {(mapping.mapping_coverage * 100).toFixed(1)}%
                  </Typography>
                </div>
                <Stack direction="row" spacing={1} flexWrap="wrap">
                  <Chip color="success" size="small" label={`${mapping.mapped_identifier_count} mapped`} />
                  <Chip color={mapping.missing_identifier_count ? 'warning' : 'default'} size="small" label={`${mapping.missing_identifier_count} missing`} />
                  <Chip color={mapping.ambiguous_identifier_count ? 'warning' : 'default'} size="small" label={`${mapping.ambiguous_identifier_count} ambiguous`} />
                  <Chip size="small" label={`${mapping.duplicate_identifier_count} duplicates`} />
                </Stack>
              </Stack>
              <Stack direction="row" spacing={2} flexWrap="wrap">
                {([
                  ['report.json', 'Mapping report'],
                  ['missing.tsv', 'Missing identifiers'],
                  ['ambiguous.tsv', 'Ambiguous identifiers'],
                ] as const).map(([document, label]) => (
                  <Link
                    key={document}
                    href={signatureMappingDownloadUrl(mapping.id, document)}
                    underline="hover"
                    sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}
                  >
                    <DownloadRoundedIcon fontSize="small" /> {label}
                  </Link>
                ))}
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                Report SHA-256: {mapping.report_sha256}
              </Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'center' }}>
                <TextField
                  select
                  label="Scoring method"
                  size="small"
                  value={scoringMethod}
                  onChange={(event) => setScoringMethod(
                    event.target.value as SignatureScoringMethod,
                  )}
                  sx={{ minWidth: 220 }}
                >
                  <MenuItem value="mean_expression">Mean expression</MenuItem>
                  <MenuItem value="mean_z_score">Mean z-score</MenuItem>
                  <MenuItem
                    value="weighted_linear"
                    disabled={!mapping.report_json.sets.every((signatureSet) =>
                      signatureSet.mapped_entries.every((entry) => entry.weight !== undefined),
                    )}
                  >
                    Weighted linear score
                  </MenuItem>
                  <MenuItem value="rank_based">Rank-based score</MenuItem>
                  <MenuItem value="gsva">GSVA (Bioconductor R)</MenuItem>
                  <MenuItem value="ssgsea">ssGSEA (Bioconductor R)</MenuItem>
                </TextField>
                <Button
                  variant="contained"
                  startIcon={<PlayArrowRoundedIcon />}
                  disabled={scoreSignature.isPending || rParametersInvalid}
                  onClick={() => scoreSignature.mutate({
                    mappingId: mapping.id,
                    name: definitionNames.get(mapping.signature_definition_id)
                      ?? 'Signature scoring',
                  })}
                  sx={{ width: 'fit-content' }}
                >
                  {scoreSignature.isPending ? 'Launching…' : 'Score signature'}
                </Button>
              </Stack>
              {(scoringMethod === 'gsva' || scoringMethod === 'ssgsea') && (
                <Stack spacing={1.5}>
                  <Alert severity="info">
                    This method runs Bioconductor GSVA in a pinned R environment. Parameters and
                    package versions are retained with the result.
                  </Alert>
                  {rParametersInvalid && (
                    <Alert severity="error">
                      Use positive method parameters and a valid minimum/maximum set-size range.
                    </Alert>
                  )}
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                    <TextField
                      label="Minimum set size"
                      size="small"
                      type="number"
                      value={minimumGeneSetSize}
                      onChange={(event) => setMinimumGeneSetSize(Number(event.target.value))}
                      inputProps={{ min: 1, max: 5000 }}
                    />
                    <TextField
                      label="Maximum set size"
                      size="small"
                      type="number"
                      value={maximumGeneSetSize}
                      onChange={(event) => setMaximumGeneSetSize(Number(event.target.value))}
                      inputProps={{ min: 1, max: 50000 }}
                    />
                    {scoringMethod === 'gsva' ? (
                      <>
                        <TextField
                          select
                          label="Kernel"
                          size="small"
                          value={gsvaKcdf}
                          onChange={(event) => setGsvaKcdf(
                            event.target.value as typeof gsvaKcdf,
                          )}
                          sx={{ minWidth: 145 }}
                        >
                          <MenuItem value="Gaussian">Gaussian</MenuItem>
                          <MenuItem value="Poisson">Poisson</MenuItem>
                          <MenuItem value="none">None</MenuItem>
                          <MenuItem value="auto">Automatic</MenuItem>
                        </TextField>
                        <TextField
                          label="Tau"
                          size="small"
                          type="number"
                          value={gsvaTau}
                          onChange={(event) => setGsvaTau(Number(event.target.value))}
                          inputProps={{ min: 0.01, max: 10, step: 0.1 }}
                        />
                      </>
                    ) : (
                      <TextField
                        label="Alpha"
                        size="small"
                        type="number"
                        value={ssgseaAlpha}
                        onChange={(event) => setSsgseaAlpha(Number(event.target.value))}
                        inputProps={{ min: 0.01, max: 10, step: 0.05 }}
                      />
                    )}
                  </Stack>
                  {scoringMethod === 'gsva' ? (
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                      <FormControlLabel
                        control={<Checkbox checked={gsvaMaxDiff} onChange={(event) => setGsvaMaxDiff(event.target.checked)} />}
                        label="Use maximum score difference"
                      />
                      <FormControlLabel
                        control={<Checkbox checked={gsvaAbsRanking} onChange={(event) => setGsvaAbsRanking(event.target.checked)} />}
                        label="Use absolute ranking"
                      />
                    </Stack>
                  ) : (
                    <FormControlLabel
                      control={<Checkbox checked={ssgseaNormalize} onChange={(event) => setSsgseaNormalize(event.target.checked)} />}
                      label="Normalize ssGSEA scores by score range"
                    />
                  )}
                </Stack>
              )}
            </Stack>
          </Paper>
        ))}
      </Stack>
    </Paper>
  )
}
