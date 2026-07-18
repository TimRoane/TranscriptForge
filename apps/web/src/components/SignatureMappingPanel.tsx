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
  fetchDesignOptions,
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
  const [scoringMethod, setScoringMethod] = useState<SignatureScoringMethod>('mean_z_score')
  const [minimumGeneSetSize, setMinimumGeneSetSize] = useState(1)
  const [maximumGeneSetSize, setMaximumGeneSetSize] = useState(5000)
  const [gsvaKcdf, setGsvaKcdf] = useState<'auto' | 'Gaussian' | 'Poisson' | 'none'>('Gaussian')
  const [gsvaTau, setGsvaTau] = useState(1)
  const [gsvaMaxDiff, setGsvaMaxDiff] = useState(true)
  const [gsvaAbsRanking, setGsvaAbsRanking] = useState(false)
  const [ssgseaAlpha, setSsgseaAlpha] = useState(0.25)
  const [ssgseaNormalize, setSsgseaNormalize] = useState(true)
  const [associationEnabled, setAssociationEnabled] = useState(false)
  const [phenotypeColumn, setPhenotypeColumn] = useState('')
  const [associationCovariates, setAssociationCovariates] = useState<string[]>([])
  const [associationBlock, setAssociationBlock] = useState('')
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
  const designOptions = useQuery({
    queryKey: ['de-design-options', preparedDatasetId],
    queryFn: ({ signal }) => fetchDesignOptions(preparedDatasetId, signal),
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
          phenotype_association: {
            enabled: associationEnabled,
            phenotype_column: associationEnabled ? phenotypeColumn : null,
            phenotype_kind: 'auto',
            covariates: associationEnabled ? associationCovariates : [],
            block_column: associationEnabled && associationBlock ? associationBlock : null,
          },
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
  const associationInvalid = associationEnabled && !phenotypeColumn
  const selectableVariables = designOptions.data?.variables.filter(
    (variable) => variable.missing_count === 0 && variable.unique_count >= 2,
  ) ?? []

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
              {mapping.mapping_coverage < 0.8 && (
                <Alert severity="warning">
                  Coverage is below the 80% recommendation threshold. Scoring remains available
                  for exploration, but interpret the result cautiously and review missing or
                  ambiguous identifiers before reporting it.
                </Alert>
              )}
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
                  <MenuItem value="mean_z_score">Mean z-score · recommended</MenuItem>
                  <MenuItem value="mean_expression">Mean expression</MenuItem>
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
                  disabled={scoreSignature.isPending || rParametersInvalid || associationInvalid}
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
              <Typography variant="body2" color="text.secondary">
                Mean z-score is the public-benchmark default for within-cohort direction, ranking,
                and association. Raw score cutoffs do not transfer between cohorts, platforms, or
                preprocessing pipelines.
              </Typography>
              <Paper variant="outlined" sx={{ p: 2, bgcolor: 'background.paper' }}>
                <Stack spacing={1.5}>
                  <FormControlLabel
                    control={(
                      <Checkbox
                        checked={associationEnabled}
                        onChange={(event) => setAssociationEnabled(event.target.checked)}
                      />
                    )}
                    label="Associate scores with a sample phenotype"
                  />
                  {associationEnabled && (
                    <>
                      <Typography variant="body2" color="text.secondary">
                        Fit one adjusted model per signature set. Subject/block IDs are treated as
                        categorical fixed effects; numeric and categorical phenotypes are detected
                        automatically.
                      </Typography>
                      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
                        <TextField
                          select
                          required
                          label="Phenotype"
                          size="small"
                          value={phenotypeColumn}
                          onChange={(event) => {
                            setPhenotypeColumn(event.target.value)
                            setAssociationCovariates((current) => current.filter(
                              (value) => value !== event.target.value,
                            ))
                            if (associationBlock === event.target.value) setAssociationBlock('')
                          }}
                          sx={{ minWidth: 190 }}
                        >
                          {selectableVariables.map((variable) => (
                            <MenuItem key={variable.name} value={variable.name}>
                              {variable.name} · {variable.kind}
                            </MenuItem>
                          ))}
                        </TextField>
                        <TextField
                          select
                          label="Covariates"
                          size="small"
                          value={associationCovariates}
                          onChange={(event) => {
                            const value = event.target.value
                            setAssociationCovariates(
                              typeof value === 'string' ? value.split(',') : value,
                            )
                          }}
                          SelectProps={{ multiple: true }}
                          sx={{ minWidth: 210 }}
                        >
                          {selectableVariables
                            .filter((variable) => (
                              variable.name !== phenotypeColumn
                              && variable.name !== associationBlock
                            ))
                            .map((variable) => (
                              <MenuItem key={variable.name} value={variable.name}>
                                {variable.name}
                              </MenuItem>
                            ))}
                        </TextField>
                        <TextField
                          select
                          label="Subject / block"
                          size="small"
                          value={associationBlock}
                          onChange={(event) => {
                            setAssociationBlock(event.target.value)
                            setAssociationCovariates((current) => current.filter(
                              (value) => value !== event.target.value,
                            ))
                          }}
                          sx={{ minWidth: 190 }}
                        >
                          <MenuItem value="">None</MenuItem>
                          {selectableVariables
                            .filter((variable) => variable.name !== phenotypeColumn)
                            .map((variable) => (
                              <MenuItem key={variable.name} value={variable.name}>
                                {variable.name}
                              </MenuItem>
                            ))}
                        </TextField>
                      </Stack>
                      {associationInvalid && (
                        <Alert severity="error">Choose a phenotype before launching.</Alert>
                      )}
                    </>
                  )}
                </Stack>
              </Paper>
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
