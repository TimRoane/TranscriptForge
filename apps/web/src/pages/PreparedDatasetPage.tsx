import ArrowBackRoundedIcon from '@mui/icons-material/ArrowBackRounded'
import ArrowForwardRoundedIcon from '@mui/icons-material/ArrowForwardRounded'
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded'
import PlayArrowRoundedIcon from '@mui/icons-material/PlayArrowRounded'
import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  FormControlLabel,
  Link,
  MenuItem,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom'

import {
  artifactDownloadUrl,
  createDifferentialExpressionAnalysis,
  createDimensionReductionAnalysis,
  fetchDataset,
  fetchDesignOptions,
  fetchFeatureMappingSummary,
  fetchPreparedDataset,
  fetchPreparedAnalyses,
  fetchQCSummary,
  fetchRunArtifacts,
  runAnalysis,
  validateDifferentialExpressionDesign,
  type DifferentialExpressionMethod,
  type DimensionReductionMethod,
} from '../api/client'
import { ErrorState, LoadingState } from '../components/ApiState'
import { SignatureMappingPanel } from '../components/SignatureMappingPanel'

const PRIMARY_VARIABLE_PRIORITY = [
  'treatment',
  'condition',
  'zone',
  'phenotype',
  'group',
  'genotype',
  'disease',
  'status',
]

const BLOCK_VARIABLE_PRIORITY = [
  'donor',
  'subject_id',
  'subject',
  'patient_id',
  'patient',
  'participant_id',
  'participant',
  'individual_id',
  'individual',
]

const SAMPLE_IDENTIFIER_NAMES = new Set([
  'cel_file',
  'file_name',
  'filename',
  'geo_accession',
  'sample_id',
  'sample_name',
])

const ANALYSIS_TYPE_LABELS = {
  dimension_reduction: 'Exploratory analysis',
  differential_expression: 'Differential expression',
  signature: 'Signature analysis',
}

function normalizedVariableName(name: string) {
  return name.trim().toLowerCase().replace(/[\s-]+/g, '_')
}

export function PreparedDatasetPage() {
  const { preparedDatasetId = '' } = useParams()
  const navigate = useNavigate()
  const [method, setMethod] = useState<DimensionReductionMethod>('pca')
  const [componentCount, setComponentCount] = useState(10)
  const [scaleFeatures, setScaleFeatures] = useState(false)
  const [topVariableFeatures, setTopVariableFeatures] = useState(500)
  const [clusterCount, setClusterCount] = useState(4)
  const [neighbors, setNeighbors] = useState(15)
  const [minDistance, setMinDistance] = useState(0.2)
  const [perplexity, setPerplexity] = useState(15)
  const [deAssay, setDeAssay] = useState('')
  const [deMethod, setDeMethod] = useState<DifferentialExpressionMethod>('auto')
  const [primaryVariable, setPrimaryVariable] = useState('')
  const [numerator, setNumerator] = useState('')
  const [denominator, setDenominator] = useState('')
  const [covariate, setCovariate] = useState('')
  const [blockColumn, setBlockColumn] = useState('')
  const [fdrThreshold, setFdrThreshold] = useState(0.05)
  const [foldChangeThreshold, setFoldChangeThreshold] = useState(1)
  const [enrichmentEnabled, setEnrichmentEnabled] = useState(false)
  const blockDefaultDataset = useRef('')
  const prepared = useQuery({
    queryKey: ['prepared-dataset', preparedDatasetId],
    queryFn: ({ signal }) => fetchPreparedDataset(preparedDatasetId, signal),
    enabled: Boolean(preparedDatasetId),
  })
  const datasetId = prepared.data?.dataset_id ?? ''
  const runId = prepared.data?.preparation_run_id ?? ''
  const dataset = useQuery({
    queryKey: ['dataset', datasetId],
    queryFn: ({ signal }) => fetchDataset(datasetId, signal),
    enabled: Boolean(datasetId),
  })
  const qc = useQuery({
    queryKey: ['qc-summary', runId],
    queryFn: ({ signal }) => fetchQCSummary(runId, signal),
    enabled: Boolean(runId),
  })
  const mapping = useQuery({
    queryKey: ['feature-mapping-summary', runId],
    queryFn: ({ signal }) => fetchFeatureMappingSummary(runId, signal),
    enabled: Boolean(runId),
  })
  const artifacts = useQuery({
    queryKey: ['run-artifacts', runId],
    queryFn: ({ signal }) => fetchRunArtifacts(runId, signal),
    enabled: Boolean(runId),
  })
  const analyses = useQuery({
    queryKey: ['prepared-analyses', preparedDatasetId],
    queryFn: ({ signal }) => fetchPreparedAnalyses(preparedDatasetId, signal),
    enabled: Boolean(preparedDatasetId),
  })
  const designOptions = useQuery({
    queryKey: ['de-design-options', preparedDatasetId],
    queryFn: ({ signal }) => fetchDesignOptions(preparedDatasetId, signal),
    enabled: Boolean(preparedDatasetId),
  })
  const categoricalVariables = useMemo(
    () => designOptions.data?.variables.filter(
      (variable) => variable.kind === 'categorical' && variable.levels.length >= 2,
    ) ?? [],
    [designOptions.data?.variables],
  )
  const blockVariables = useMemo(
    () => designOptions.data?.variables.filter((variable) => (
      variable.missing_count === 0
      && variable.unique_count >= 2
      && variable.unique_count < designOptions.data.sample_count
    )) ?? [],
    [designOptions.data],
  )
  const selectedPrimary = categoricalVariables.find((variable) => variable.name === primaryVariable)
  useEffect(() => {
    if (categoricalVariables.length === 0) return
    if (!categoricalVariables.some((variable) => variable.name === primaryVariable)) {
      const preferred = PRIMARY_VARIABLE_PRIORITY
        .map((name) => categoricalVariables.find(
          (variable) => normalizedVariableName(variable.name) === name,
        ))
        .find((variable) => variable !== undefined)
        ?? categoricalVariables.find((variable) => (
          variable.unique_count < (designOptions.data?.sample_count ?? Number.POSITIVE_INFINITY)
          && !SAMPLE_IDENTIFIER_NAMES.has(normalizedVariableName(variable.name))
        ))
        ?? categoricalVariables[0]
      setPrimaryVariable(preferred.name)
    }
  }, [categoricalVariables, designOptions.data?.sample_count, primaryVariable])
  useEffect(() => {
    if (!designOptions.data || blockDefaultDataset.current === preparedDatasetId) return
    blockDefaultDataset.current = preparedDatasetId
    const preferred = BLOCK_VARIABLE_PRIORITY
      .map((name) => blockVariables.find(
        (variable) => normalizedVariableName(variable.name) === name,
      ))
      .find((variable) => variable !== undefined)
    if (preferred && preferred.name !== primaryVariable && preferred.name !== covariate) {
      setBlockColumn(preferred.name)
    }
  }, [blockVariables, covariate, designOptions.data, preparedDatasetId, primaryVariable])
  useEffect(() => {
    if (
      blockColumn
      && (
        blockColumn === primaryVariable
        || blockColumn === covariate
        || !blockVariables.some((variable) => variable.name === blockColumn)
      )
    ) {
      setBlockColumn('')
    }
  }, [blockColumn, blockVariables, covariate, primaryVariable])
  useEffect(() => {
    if (!selectedPrimary) return
    const reference = selectedPrimary.levels.find((level) =>
      ['control', 'vehicle', 'untreated', 'baseline', 'wild_type'].includes(level.toLowerCase()),
    ) ?? selectedPrimary.levels[0]
    const comparison = selectedPrimary.levels.find((level) =>
      ['treated', 'stimulated', 'case', 'mutant'].includes(level.toLowerCase()),
    ) ?? selectedPrimary.levels.find((level) => level !== reference) ?? selectedPrimary.levels[0]
    if (!selectedPrimary.levels.includes(numerator)) {
      setNumerator(comparison)
    }
    if (!selectedPrimary.levels.includes(denominator)) {
      setDenominator(reference)
    }
  }, [denominator, numerator, selectedPrimary])
  useEffect(() => {
    if (!prepared.data) return
    if (!prepared.data.value_types_available.includes(deAssay)) {
      setDeAssay(
        prepared.data.value_types_available.includes('raw_counts')
          ? 'raw_counts'
          : prepared.data.value_types_available[0] ?? 'log_expression',
      )
    }
  }, [deAssay, prepared.data])
  const deParameters = {
    design: {
      primary_variable: primaryVariable,
      covariates: covariate ? [covariate] : [],
      block_column: blockColumn || null,
      interaction_terms: [] as Array<[string, string]>,
      reference_levels: denominator && primaryVariable
        ? { [primaryVariable]: denominator }
        : {},
    },
    contrast: { variable: primaryVariable, numerator, denominator },
    fdr_threshold: fdrThreshold,
    absolute_log2_fold_change: foldChangeThreshold,
    enrichment: {
      enabled: enrichmentEnabled,
      collection_id: 'transcriptforge_demo_effects',
      ranking_metric: 'signed_log10_p_value' as const,
      permutation_count: 250,
      minimum_gene_set_size: 10,
      maximum_gene_set_size: 500,
    },
  }
  const designValidation = useQuery({
    queryKey: [
      'de-design-validation', preparedDatasetId, deAssay, deMethod, primaryVariable,
      numerator, denominator, covariate, blockColumn, fdrThreshold, foldChangeThreshold,
      enrichmentEnabled,
    ],
    queryFn: ({ signal }) => validateDifferentialExpressionDesign(
      preparedDatasetId,
      { assay: deAssay, method: deMethod, parameters: deParameters },
      signal,
    ),
    enabled: Boolean(
      deAssay && primaryVariable && numerator && denominator && numerator !== denominator,
    ),
  })
  const launchAnalysis = useMutation({
    mutationFn: async () => {
      const assay = prepared.data?.value_types_available.includes('log_expression')
        ? 'log_expression'
        : prepared.data?.value_types_available[0] ?? 'normalized_expression'
      const names = {
        pca: 'Principal component analysis',
        hierarchical_clustering: 'Hierarchical sample clustering',
        umap: 'UMAP embedding',
        tsne: 't-SNE embedding',
      }
      const analysis = await createDimensionReductionAnalysis(preparedDatasetId, {
        name: names[method],
        method,
        assay,
        parameters: {
          component_count: componentCount,
          scale_features: scaleFeatures,
          top_variable_features: topVariableFeatures,
          cluster_count: clusterCount,
          neighbors,
          min_distance: minDistance,
          perplexity,
        },
        random_seed: 20260716,
      })
      await runAnalysis(analysis.id)
      return analysis
    },
    onSuccess: (analysis) => navigate(`/analyses/${analysis.id}`),
  })
  const saveDifferentialExpression = useMutation({
    mutationFn: () => createDifferentialExpressionAnalysis(preparedDatasetId, {
      name: `${numerator} versus ${denominator}`,
      analysis_type: 'differential_expression',
      assay: deAssay,
      method: deMethod,
      parameters: deParameters,
      random_seed: 20260716,
    }),
    onSuccess: (analysis) => navigate(`/analyses/${analysis.id}`),
  })

  if (prepared.isPending) return <LoadingState label="Loading prepared dataset…" />
  if (prepared.isError) return <ErrorState error={prepared.error} />

  const isMicroarray = dataset.data?.source_kind === 'affymetrix_cel'
  const matrixQC = qc.data && 'samples' in qc.data ? qc.data : null
  const microarrayQC = qc.data && 'probe_count' in qc.data ? qc.data : null
  const maxLibrary = Math.max(...(matrixQC?.samples.map((sample) => sample.library_size) ?? [1]))
  const reviewFlags = matrixQC?.flags.filter((flag) => flag.status === 'REVIEW') ?? []
  const microarrayPlots = artifacts.data?.filter((artifact) => [
    'microarray_raw_boxplot',
    'microarray_normalized_boxplot',
    'microarray_pca',
    'microarray_sample_correlation',
  ].includes(artifact.artifact_type)) ?? []

  return (
    <Stack spacing={3}>
      {dataset.data && (
        <Link
          component={RouterLink}
          to={`/projects/${dataset.data.project_id}`}
          underline="hover"
          sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, width: 'fit-content' }}
        >
          <ArrowBackRoundedIcon fontSize="small" /> {dataset.data.name}
        </Link>
      )}
      <div>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Typography variant="h3" fontWeight={750}>Expression Bundle</Typography>
          <Chip label={`Version ${prepared.data.version}`} color="primary" />
          <Chip
            label={`QC ${prepared.data.qc_status}`}
            color={prepared.data.qc_status === 'PASS' ? 'success' : 'warning'}
          />
        </Stack>
        <Typography color="text.secondary" mt={1}>
          Immutable, analysis-ready human expression data with mapping and provenance contracts.
        </Typography>
      </div>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
        {[
          ['Samples', prepared.data.sample_count.toLocaleString()],
          ['Features', prepared.data.feature_count.toLocaleString()],
          ['Assays', prepared.data.value_types_available.join(', ')],
          ['Mapping coverage', mapping.data ? `${(mapping.data.mapping_coverage * 100).toFixed(1)}%` : '…'],
        ].map(([label, value]) => (
          <Paper variant="outlined" sx={{ p: 2, flex: 1 }} key={label}>
            <Typography variant="overline" color="text.secondary">{label}</Typography>
            <Typography variant="h6" fontWeight={700}>{value}</Typography>
          </Paper>
        ))}
      </Stack>

      {(analyses.data?.length ?? 0) > 0 && (
        <Paper
          variant="outlined"
          sx={{ p: 3, borderWidth: 2, borderColor: 'primary.light' }}
        >
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            justifyContent="space-between"
            alignItems={{ sm: 'center' }}
            gap={1}
          >
            <Box>
              <Typography variant="overline" color="primary.main" fontWeight={750}>
                Continue your work
              </Typography>
              <Typography variant="h5" fontWeight={700}>Saved analyses</Typography>
              <Typography color="text.secondary" mt={0.5}>
                Open an analysis to view its results, check run status, or launch a saved design.
              </Typography>
            </Box>
            <Chip label={`${analyses.data?.length ?? 0} saved`} color="primary" />
          </Stack>
          <Box
            mt={2}
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', lg: 'repeat(2, minmax(0, 1fr))' },
              gap: 1.5,
            }}
          >
            {analyses.data?.map((analysis) => (
              <Button
                key={analysis.id}
                component={RouterLink}
                to={`/analyses/${analysis.id}`}
                variant="outlined"
                endIcon={<ArrowForwardRoundedIcon />}
                sx={{
                  p: 2,
                  minHeight: 82,
                  justifyContent: 'space-between',
                  textAlign: 'left',
                  textTransform: 'none',
                }}
              >
                <Box>
                  <Typography variant="overline" color="text.secondary" lineHeight={1.2}>
                    {ANALYSIS_TYPE_LABELS[analysis.analysis_type]}
                  </Typography>
                  <Typography variant="subtitle1" color="text.primary" fontWeight={700}>
                    {analysis.name}
                  </Typography>
                  <Typography variant="body2" color="primary.main" fontWeight={650}>
                    Open analysis
                  </Typography>
                </Box>
              </Button>
            ))}
          </Box>
        </Paper>
      )}

      {isMicroarray ? (
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h5" fontWeight={700}>Array QC</Typography>
          <Typography color="text.secondary" mt={0.5}>
            Raw and RMA-normalized distributions, sample correlation, and PCA. Review flags never
            remove arrays automatically.
          </Typography>
          {qc.isPending && <LoadingState label="Loading array QC…" />}
          {qc.isError && <ErrorState error={qc.error} />}
          {microarrayQC && (
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} mt={2} flexWrap="wrap">
              <Chip label={`${microarrayQC.sample_count.toLocaleString()} arrays`} />
              <Chip label={`${microarrayQC.probe_count.toLocaleString()} probe sets`} />
              <Chip label={`${microarrayQC.gene_count.toLocaleString()} genes`} />
              <Chip
                label={`${microarrayQC.reviewed_sample_count} flagged for review`}
                color={microarrayQC.reviewed_sample_count > 0 ? 'warning' : 'success'}
              />
            </Stack>
          )}
          <Box
            mt={2.5}
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', lg: 'repeat(2, minmax(0, 1fr))' },
              gap: 2,
            }}
          >
            {microarrayPlots.map((artifact) => (
              <Paper variant="outlined" sx={{ p: 1.5 }} key={artifact.id}>
                <Typography variant="subtitle2" mb={1}>{artifact.title}</Typography>
                <Box
                  component="img"
                  src={artifactDownloadUrl(artifact.id)}
                  alt={artifact.title}
                  sx={{ display: 'block', width: '100%', height: 'auto' }}
                />
              </Paper>
            ))}
          </Box>
        </Paper>
      ) : (
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h5" fontWeight={700}>Sample QC</Typography>
          <Typography color="text.secondary" mt={0.5}>
            Library size and detected-feature summaries. Samples are flagged for review, never automatically removed.
          </Typography>
          {qc.isPending && <LoadingState label="Loading QC metrics…" />}
          {qc.isError && <ErrorState error={qc.error} />}
          {reviewFlags.length > 0 && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              {reviewFlags.length} sample{reviewFlags.length === 1 ? '' : 's'} flagged for review.
            </Alert>
          )}
          <Stack spacing={1.5} mt={2}>
            {matrixQC?.samples.map((sample) => (
              <Box key={sample.sample_id}>
                <Stack direction="row" justifyContent="space-between" gap={2}>
                  <Typography variant="body2" fontWeight={650}>{sample.sample_id}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {sample.library_size.toLocaleString()} total · {sample.detected_features.toLocaleString()} detected
                  </Typography>
                </Stack>
                <Box sx={{ height: 10, bgcolor: 'grey.200', borderRadius: 5, mt: 0.5, overflow: 'hidden' }}>
                  <Box
                    sx={{
                      width: `${maxLibrary > 0 ? (sample.library_size / maxLibrary) * 100 : 0}%`,
                      height: '100%',
                      bgcolor: 'primary.main',
                    }}
                  />
                </Box>
              </Box>
            ))}
          </Stack>
        </Paper>
      )}

      <Paper variant="outlined" sx={{ p: 3 }}>
        <Stack spacing={2.5}>
          <Box>
            <Typography variant="overline" color="secondary.main" fontWeight={750}>
              Differential expression
            </Typography>
            <Typography variant="h5" fontWeight={700}>Define the biological comparison</Typography>
            <Typography color="text.secondary" mt={0.5}>
              Build and validate the model before saving it. The exact formula, contrast,
              replication, and method routing remain visible.
            </Typography>
          </Box>

          {designOptions.isError && <ErrorState error={designOptions.error} />}
          <Stack
            direction={{ xs: 'column', md: 'row' }}
            spacing={2}
            alignItems={{ md: 'center' }}
            flexWrap="wrap"
          >
            <TextField
              select
              label="Assay"
              size="small"
              value={deAssay}
              onChange={(event) => setDeAssay(event.target.value)}
              sx={{ minWidth: 165 }}
            >
              {prepared.data.value_types_available.map((assay) => (
                <MenuItem key={assay} value={assay}>{assay}</MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Method"
              size="small"
              value={deMethod}
              onChange={(event) => setDeMethod(event.target.value as DifferentialExpressionMethod)}
              sx={{ minWidth: 145 }}
            >
              <MenuItem value="auto">Automatic</MenuItem>
              <MenuItem value="deseq2">DESeq2</MenuItem>
              <MenuItem value="limma">limma</MenuItem>
              <MenuItem value="edger_ql">edgeR QL</MenuItem>
              <MenuItem value="limma_voom">limma-voom</MenuItem>
            </TextField>
            <TextField
              select
              label="Primary variable"
              size="small"
              value={primaryVariable}
              onChange={(event) => setPrimaryVariable(event.target.value)}
              sx={{ minWidth: 175 }}
            >
              {categoricalVariables.length === 0 && (
                <MenuItem value="" disabled>No categorical variables</MenuItem>
              )}
              {categoricalVariables.map((variable) => (
                <MenuItem key={variable.name} value={variable.name}>
                  {variable.name} ({variable.levels.length} levels)
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Numerator"
              size="small"
              value={numerator}
              onChange={(event) => setNumerator(event.target.value)}
              sx={{ minWidth: 145 }}
            >
              {(selectedPrimary?.levels.length ?? 0) === 0 && (
                <MenuItem value="" disabled>Select a variable first</MenuItem>
              )}
              {selectedPrimary?.levels.map((level) => (
                <MenuItem key={level} value={level}>{level}</MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Denominator"
              size="small"
              value={denominator}
              onChange={(event) => setDenominator(event.target.value)}
              sx={{ minWidth: 145 }}
            >
              {(selectedPrimary?.levels.length ?? 0) === 0 && (
                <MenuItem value="" disabled>Select a variable first</MenuItem>
              )}
              {selectedPrimary?.levels.map((level) => (
                <MenuItem key={level} value={level}>{level}</MenuItem>
              ))}
            </TextField>
          </Stack>

          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} flexWrap="wrap">
            <TextField
              select
              label="Adjust for"
              size="small"
              value={covariate}
              onChange={(event) => setCovariate(event.target.value)}
              sx={{ minWidth: 175 }}
            >
              <MenuItem value="">No covariate</MenuItem>
              {designOptions.data?.variables
                .filter((variable) => variable.name !== primaryVariable && variable.missing_count === 0)
                .map((variable) => (
                  <MenuItem key={variable.name} value={variable.name}>{variable.name}</MenuItem>
                ))}
            </TextField>
            <TextField
              select
              label="Subject / block"
              size="small"
              value={blockColumn}
              onChange={(event) => setBlockColumn(event.target.value)}
              sx={{ minWidth: 175 }}
            >
              <MenuItem value="">No block</MenuItem>
              {blockVariables
                .filter((variable) => variable.name !== primaryVariable && variable.name !== covariate)
                .map((variable) => (
                  <MenuItem key={variable.name} value={variable.name}>
                    {variable.name} ({variable.unique_count} IDs)
                  </MenuItem>
                ))}
            </TextField>
            <TextField
              label="FDR threshold"
              type="number"
              size="small"
              value={fdrThreshold}
              onChange={(event) => setFdrThreshold(
                Math.min(1, Math.max(0.001, Number(event.target.value))),
              )}
              inputProps={{ min: 0.001, max: 1, step: 0.01 }}
              sx={{ width: 145 }}
            />
            <TextField
              label="Absolute log2 FC"
              type="number"
              size="small"
              value={foldChangeThreshold}
              onChange={(event) => setFoldChangeThreshold(
                Math.max(0, Number(event.target.value)),
              )}
              inputProps={{ min: 0, step: 0.25 }}
              sx={{ width: 155 }}
            />
          </Stack>

          <Paper variant="outlined" sx={{ p: 2.5, bgcolor: 'background.default' }}>
            <FormControlLabel
              control={(
                <Switch
                  checked={enrichmentEnabled}
                  onChange={(event) => setEnrichmentEnabled(event.target.checked)}
                />
              )}
              label="Run optional gene-set enrichment"
            />
            <Typography variant="body2" color="text.secondary">
              Runs deterministic ranked-list enrichment and over-representation analysis after
              differential expression. The collection version and SHA-256 are frozen in the result.
            </Typography>
            {enrichmentEnabled && (
              <Alert severity="warning" sx={{ mt: 1.5 }}>
                The bundled “TranscriptForge simulated-effect controls” collection is designed for
                the deterministic demonstration study. It is not a curated biological pathway database.
              </Alert>
            )}
          </Paper>

          {designValidation.data && (
            <Paper variant="outlined" sx={{ p: 2.5, bgcolor: 'background.default' }}>
              <Stack spacing={1.5}>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
                  <Chip
                    label={designValidation.data.valid ? 'Design valid' : 'Design blocked'}
                    color={designValidation.data.valid ? 'success' : 'error'}
                  />
                  <Chip label={`Method: ${designValidation.data.resolved_method}`} variant="outlined" />
                  <Chip
                    label={`Rank ${designValidation.data.design_matrix_rank}/${designValidation.data.design_matrix_columns.length}`}
                    variant="outlined"
                  />
                </Stack>
                <Typography variant="overline" color="text.secondary">Generated formula</Typography>
                <Typography component="code" sx={{ fontFamily: 'monospace', fontSize: '1rem' }}>
                  {designValidation.data.formula}
                </Typography>
                <Typography><strong>Contrast:</strong> {designValidation.data.contrast_label}</Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap">
                  {Object.entries(designValidation.data.contrast_counts).map(([level, count]) => (
                    <Chip key={level} size="small" label={`${level}: ${count} samples`} />
                  ))}
                </Stack>
                {designValidation.data.errors.map((message) => (
                  <Alert key={message} severity="error">{message}</Alert>
                ))}
                {designValidation.data.warnings.map((message) => (
                  <Alert key={message} severity="warning">{message}</Alert>
                ))}
              </Stack>
            </Paper>
          )}

          <Box>
            <Button
              variant="contained"
              endIcon={<ArrowForwardRoundedIcon />}
              onClick={() => saveDifferentialExpression.mutate()}
              disabled={!designValidation.data?.valid || saveDifferentialExpression.isPending}
              sx={{ width: { xs: '100%', sm: 'fit-content' } }}
            >
              {saveDifferentialExpression.isPending
                ? 'Saving design…'
                : 'Save design & continue to run'}
            </Button>
            <Typography variant="body2" color="text.secondary" mt={1}>
              Opens the saved analysis page, where you can review the frozen model and start the run.
            </Typography>
          </Box>
          {saveDifferentialExpression.isError && (
            <Alert severity="error">{saveDifferentialExpression.error.message}</Alert>
          )}
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography variant="h5" fontWeight={700}>Feature harmonization</Typography>
        <Divider sx={{ my: 2 }} />
        {mapping.data && (
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3}>
            <Typography>{mapping.data.mapped_feature_count.toLocaleString()} mapped</Typography>
            <Typography>{mapping.data.unmapped_feature_count.toLocaleString()} unmapped</Typography>
            {isMicroarray ? (
              <>
                <Typography>
                  {(mapping.data.probe_count ?? 0).toLocaleString()} probe sets retained
                </Typography>
                <Typography>
                  Aggregation: {(mapping.data.aggregation_method ?? 'unknown').replace('_', ' ')}
                </Typography>
              </>
            ) : (
              <Typography>
                {mapping.data.duplicate_group_count.toLocaleString()} duplicate groups resolved by sum
              </Typography>
            )}
          </Stack>
        )}
      </Paper>

      {dataset.data && (
        <SignatureMappingPanel
          preparedDatasetId={preparedDatasetId}
          projectId={dataset.data.project_id}
        />
      )}

      <Paper variant="outlined" sx={{ p: 3 }}>
        <Stack spacing={2.5}>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={3} alignItems={{ md: 'flex-end' }}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="overline" color="secondary.main" fontWeight={750}>
              Exploratory analysis
            </Typography>
            <Typography variant="h5" fontWeight={700}>Explore sample structure</Typography>
            <Typography color="text.secondary" mt={0.5}>
              Run PCA, hierarchical clustering, UMAP, or t-SNE over a frozen analysis-ready assay.
            </Typography>
          </Box>
          <TextField select label="Method" size="small" value={method} onChange={(event) => setMethod(event.target.value as typeof method)} sx={{ minWidth: 220 }}>
            <MenuItem value="pca">PCA</MenuItem>
            <MenuItem value="hierarchical_clustering">Hierarchical clustering</MenuItem>
            <MenuItem value="umap">UMAP</MenuItem>
            <MenuItem value="tsne">t-SNE</MenuItem>
          </TextField>
          </Stack>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }} flexWrap="wrap">
          {method === 'pca' && (
            <TextField
              label="Components"
              type="number"
              size="small"
              value={componentCount}
              onChange={(event) => setComponentCount(Math.min(20, Math.max(2, Number(event.target.value))))}
              inputProps={{ min: 2, max: 20 }}
              sx={{ width: 130 }}
            />
          )}
          {method !== 'pca' && (
            <TextField
              label="Variable features"
              type="number"
              size="small"
              value={topVariableFeatures}
              onChange={(event) => setTopVariableFeatures(Math.min(prepared.data.feature_count, Math.max(10, Number(event.target.value))))}
              inputProps={{ min: 10, max: prepared.data.feature_count }}
              sx={{ width: 160 }}
            />
          )}
          {method === 'hierarchical_clustering' && (
            <TextField label="Clusters" type="number" size="small" value={clusterCount} onChange={(event) => setClusterCount(Math.min(20, Math.max(2, Number(event.target.value))))} inputProps={{ min: 2, max: 20 }} sx={{ width: 120 }} />
          )}
          {method === 'umap' && (
            <>
              <TextField label="Neighbors" type="number" size="small" value={neighbors} onChange={(event) => setNeighbors(Math.min(prepared.data.sample_count - 1, Math.max(2, Number(event.target.value))))} sx={{ width: 120 }} />
              <TextField label="Min. distance" type="number" size="small" value={minDistance} onChange={(event) => setMinDistance(Math.min(0.99, Math.max(0, Number(event.target.value))))} inputProps={{ min: 0, max: 0.99, step: 0.05 }} sx={{ width: 135 }} />
            </>
          )}
          {method === 'tsne' && (
            <TextField label="Perplexity" type="number" size="small" value={perplexity} onChange={(event) => setPerplexity(Math.min(prepared.data.sample_count - 1, Math.max(2, Number(event.target.value))))} sx={{ width: 125 }} />
          )}
          <FormControlLabel
            control={<Switch checked={scaleFeatures} onChange={(_, checked) => setScaleFeatures(checked)} />}
            label="Scale features"
          />
          <Button
            variant="contained"
            startIcon={<PlayArrowRoundedIcon />}
            onClick={() => launchAnalysis.mutate()}
            disabled={launchAnalysis.isPending}
          >
            {launchAnalysis.isPending ? 'Launching…' : 'Run analysis'}
          </Button>
        </Stack>
        </Stack>
        {launchAnalysis.isError && <Alert severity="error" sx={{ mt: 2 }}>{launchAnalysis.error.message}</Alert>}
      </Paper>

      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography variant="h5" fontWeight={700}>Downloads and provenance</Typography>
        <Stack direction="row" spacing={2} mt={2} flexWrap="wrap">
          {artifacts.data
            ?.filter((artifact) => [
              'expression_bundle',
              'bundle_manifest',
              'qc_summary',
              'feature_mapping_summary',
              'microarray_gene_expression',
              'microarray_probe_expression',
              'microarray_probe_mapping',
              'microarray_qc_metrics',
              'microarray_r_session',
              'nextflow_report',
              'nextflow_trace',
            ].includes(artifact.artifact_type))
            .map((artifact) => (
              <Link
                key={artifact.id}
                href={artifactDownloadUrl(artifact.id)}
                underline="hover"
                sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}
              >
                <DownloadRoundedIcon fontSize="small" /> {artifact.title}
              </Link>
            ))}
        </Stack>
      </Paper>

      <Alert severity="info">
        Research use only. This prepared dataset is not clinically validated.
      </Alert>
    </Stack>
  )
}
