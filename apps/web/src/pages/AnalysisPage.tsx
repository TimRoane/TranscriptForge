import ArrowBackRoundedIcon from '@mui/icons-material/ArrowBackRounded'
import CloseRoundedIcon from '@mui/icons-material/CloseRounded'
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded'
import PlayArrowRoundedIcon from '@mui/icons-material/PlayArrowRounded'
import ReplayRoundedIcon from '@mui/icons-material/ReplayRounded'
import StopCircleRoundedIcon from '@mui/icons-material/StopCircleRounded'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  Link,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  TextField,
  Typography,
} from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useParams } from 'react-router-dom'

import {
  artifactDownloadUrl,
  cancelRun,
  createGeneSignature,
  fetchAnalysis,
  fetchAnalysisRuns,
  fetchCorrelationHeatmap,
  fetchClassifierResults,
  fetchDendrogramPlot,
  fetchDifferentialExpressionFeature,
  fetchDifferentialExpressionResults,
  fetchDeconvolutionComparison,
  fetchDeconvolutionResults,
  fetchEmbeddingPlot,
  fetchEnrichmentSummary,
  fetchExpressionHeatmap,
  fetchMAPlot,
  fetchPCAPlot,
  fetchPreparedDataset,
  fetchPValueDistribution,
  fetchResultManifest,
  fetchRunArtifacts,
  fetchRunSignatures,
  fetchSignatureScores,
  fetchVariancePlot,
  fetchVolcanoPlot,
  filteredDifferentialExpressionDownloadUrl,
  runAnalysis,
  type Artifact,
  type CorrelationHeatmap,
  type DendrogramPlot,
  type DifferentialExpressionFeatureDetail,
  type DifferentialExpressionPlot,
  type DifferentialExpressionResultQuery,
  type DifferentialExpressionSort,
  type DeconvolutionComparison,
  type DeconvolutionResults,
  type EmbeddingPlot,
  type EnrichmentResult,
  type EnrichmentSummary,
  type ExpressionHeatmap,
  type PValueDistribution,
  type Run,
  type SignatureScores,
} from '../api/client'
import { ErrorState, LoadingState } from '../components/ApiState'

const activeStates = new Set<Run['state']>([
  'CREATED',
  'QUEUED',
  'STARTING',
  'RUNNING',
  'CANCELLING',
])
const colors = ['#155e75', '#7c3aed', '#d97706', '#be123c', '#15803d', '#0369a1', '#9333ea']

export function AnalysisPage() {
  const { analysisId = '' } = useParams()
  const [selectedFeature, setSelectedFeature] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const analysis = useQuery({
    queryKey: ['analysis', analysisId],
    queryFn: ({ signal }) => fetchAnalysis(analysisId, signal),
    enabled: Boolean(analysisId),
  })
  const runs = useQuery({
    queryKey: ['analysis-runs', analysisId],
    queryFn: ({ signal }) => fetchAnalysisRuns(analysisId, signal),
    enabled: Boolean(analysisId),
    refetchInterval: (query) => {
      const latest = query.state.data?.[0]
      return latest && activeStates.has(latest.state) ? 1200 : false
    },
  })
  const latest = runs.data?.[0]
  const prepared = useQuery({
    queryKey: ['prepared-dataset', analysis.data?.prepared_dataset_id],
    queryFn: ({ signal }) => fetchPreparedDataset(analysis.data!.prepared_dataset_id, signal),
    enabled: Boolean(analysis.data?.prepared_dataset_id),
  })
  const succeeded = latest?.state === 'SUCCEEDED'
  const method = analysis.data?.configuration_json.method
  const plot = useQuery({
    queryKey: ['pca-plot', latest?.id],
    queryFn: ({ signal }) => fetchPCAPlot(latest!.id, signal),
    enabled: succeeded && method === 'pca',
  })
  const variance = useQuery({
    queryKey: ['variance-plot', latest?.id],
    queryFn: ({ signal }) => fetchVariancePlot(latest!.id, signal),
    enabled: succeeded && method === 'pca',
  })
  const embedding = useQuery({
    queryKey: ['embedding-plot', latest?.id],
    queryFn: ({ signal }) => fetchEmbeddingPlot(latest!.id, signal),
    enabled: succeeded && (method === 'umap' || method === 'tsne'),
  })
  const dendrogram = useQuery({
    queryKey: ['dendrogram-plot', latest?.id],
    queryFn: ({ signal }) => fetchDendrogramPlot(latest!.id, signal),
    enabled: succeeded && method === 'hierarchical_clustering',
  })
  const heatmap = useQuery({
    queryKey: ['correlation-heatmap', latest?.id],
    queryFn: ({ signal }) => fetchCorrelationHeatmap(latest!.id, signal),
    enabled: succeeded && method === 'hierarchical_clustering',
  })
  const volcano = useQuery({
    queryKey: ['volcano-plot', latest?.id],
    queryFn: ({ signal }) => fetchVolcanoPlot(latest!.id, signal),
    enabled: succeeded && analysis.data?.analysis_type === 'differential_expression',
  })
  const maPlot = useQuery({
    queryKey: ['ma-plot', latest?.id],
    queryFn: ({ signal }) => fetchMAPlot(latest!.id, signal),
    enabled: succeeded && analysis.data?.analysis_type === 'differential_expression',
  })
  const pValueDistribution = useQuery({
    queryKey: ['p-value-distribution', latest?.id],
    queryFn: ({ signal }) => fetchPValueDistribution(latest!.id, signal),
    enabled: succeeded && analysis.data?.analysis_type === 'differential_expression',
  })
  const expressionHeatmap = useQuery({
    queryKey: ['expression-heatmap', latest?.id],
    queryFn: ({ signal }) => fetchExpressionHeatmap(latest!.id, signal),
    enabled: succeeded && analysis.data?.analysis_type === 'differential_expression',
  })
  const enrichment = useQuery({
    queryKey: ['enrichment-summary', latest?.id],
    queryFn: ({ signal }) => fetchEnrichmentSummary(latest!.id, signal),
    enabled: succeeded
      && analysis.data?.configuration_json.analysis_type === 'differential_expression'
      && Boolean(analysis.data.configuration_json.parameters.enrichment?.enabled),
  })
  const signatureScores = useQuery({
    queryKey: ['signature-scores', latest?.id],
    queryFn: ({ signal }) => fetchSignatureScores(latest!.id, signal),
    enabled: succeeded && analysis.data?.analysis_type === 'signature',
  })
  const deconvolutionResults = useQuery({
    queryKey: ['deconvolution-results', latest?.id],
    queryFn: ({ signal }) => fetchDeconvolutionResults(latest!.id, signal),
    enabled: succeeded && analysis.data?.analysis_type === 'deconvolution',
  })
  const classifierResults = useQuery({
    queryKey: ['classifier-results', latest?.id],
    queryFn: ({ signal }) => fetchClassifierResults(latest!.id, signal),
    enabled: succeeded && analysis.data?.analysis_type === 'classifier',
  })
  const deconvolutionComparison = useQuery({
    queryKey: [
      'deconvolution-comparison',
      analysis.data?.prepared_dataset_id,
      latest?.id,
    ],
    queryFn: ({ signal }) => fetchDeconvolutionComparison(
      analysis.data!.prepared_dataset_id,
      signal,
    ),
    enabled: succeeded && analysis.data?.analysis_type === 'deconvolution',
  })
  const manifest = useQuery({
    queryKey: ['result-manifest', latest?.id],
    queryFn: ({ signal }) => fetchResultManifest(latest!.id, signal),
    enabled: succeeded,
  })
  const artifacts = useQuery({
    queryKey: ['run-artifacts', latest?.id],
    queryFn: ({ signal }) => fetchRunArtifacts(latest!.id, signal),
    enabled: succeeded,
  })
  const rerun = useMutation({
    mutationFn: () => runAnalysis(analysisId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['analysis-runs', analysisId] }),
  })
  const cancel = useMutation({
    mutationFn: (runId: string) => cancelRun(runId),
    onSuccess: (cancelledRun) => {
      queryClient.setQueryData<Run[]>(['analysis-runs', analysisId], (current) =>
        current?.map((run) => (run.id === cancelledRun.id ? cancelledRun : run)),
      )
      return queryClient.invalidateQueries({ queryKey: ['analysis-runs', analysisId] })
    },
  })

  if (analysis.isPending || runs.isPending) return <LoadingState label="Loading analysis…" />
  if (analysis.isError) return <ErrorState error={analysis.error} />
  if (runs.isError) return <ErrorState error={runs.error} />

  const configuration = analysis.data.configuration_json
  if (configuration.analysis_type === 'classifier') {
    const validation = configuration.design_validation
    const active = Boolean(latest && activeStates.has(latest.state))
    const classifierDiagnosticImage = artifacts.data?.find(
      (artifact) => artifact.artifact_type === 'classifier_diagnostics_svg',
    )
    const multiclassDiagnostics = classifierResults.data?.method === 'multinomial_elastic_net'
      ? classifierResults.data.diagnostics
      : null
    return (
      <Stack spacing={3}>
        <Link
          component={RouterLink}
          to={`/prepared-datasets/${analysis.data.prepared_dataset_id}`}
          underline="hover"
          sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, width: 'fit-content' }}
        >
          <ArrowBackRoundedIcon fontSize="small" /> Expression Bundle v{prepared.data?.version ?? '…'}
        </Link>
        <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" gap={2}>
          <Box>
            <Typography variant="overline" color="secondary.main" fontWeight={750}>
              Classifier development · saved validation design
            </Typography>
            <Typography variant="h3" fontWeight={750}>{analysis.data.name}</Typography>
            <Typography color="text.secondary" mt={1}>
              {configuration.method === 'multinomial_elastic_net'
                ? `Multinomial elastic-net logistic regression · ${configuration.assay} · ${validation.class_labels.length} classes`
                : `Binary elastic-net logistic regression · ${configuration.assay} · positive class ${configuration.parameters.positive_class}`}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} alignItems="center">
            {latest && <RunStateChip run={latest} />}
            {active && latest ? (
              <CancelRunButton run={latest} pending={cancel.isPending} onCancel={cancel.mutate} />
            ) : (
              <Button
                variant={latest ? 'outlined' : 'contained'}
                startIcon={latest ? <ReplayRoundedIcon /> : <PlayArrowRoundedIcon />}
                onClick={() => rerun.mutate()}
                disabled={rerun.isPending}
              >
                {rerun.isPending ? 'Queueing…' : latest ? 'Run again' : 'Run classifier'}
              </Button>
            )}
          </Stack>
        </Stack>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          {[
            ['Eligible samples', validation.eligible_sample_count.toLocaleString()],
            ['Experimental units', validation.group_count.toLocaleString()],
            ['Validation', `${validation.outer_folds}-fold × ${validation.repeats} repeats`],
            ['Planned OOF predictions', validation.expected_oof_prediction_count.toLocaleString()],
          ].map(([label, value]) => (
            <Paper key={label} variant="outlined" sx={{ p: 2, flex: 1 }}>
              <Typography variant="overline" color="text.secondary">{label}</Typography>
              <Typography variant="h6" fontWeight={700}>{value}</Typography>
            </Paper>
          ))}
        </Stack>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Stack spacing={2}>
            <div>
              <Typography variant="h5" fontWeight={700}>Outcome and validation</Typography>
              <Typography color="text.secondary" mt={0.5}>
                {configuration.parameters.outcome_column}: {validation.negative_class} versus{' '}
                {validation.positive_class}
                {configuration.parameters.group_column
                  ? `, grouped by ${configuration.parameters.group_column}`
                  : ', with independent samples'}.
              </Typography>
            </div>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {Object.entries(validation.class_counts).map(([level, count]) => (
                <Chip key={level} label={`${level}: ${count} samples`} />
              ))}
              <Chip label={`${validation.inner_folds}-fold inner tuning`} />
              <Chip label={`${configuration.parameters.top_variable_features} variable genes`} />
              <Chip label={`${configuration.parameters.primary_metric.replaceAll('_', ' ')} primary metric`} />
            </Stack>
          </Stack>
        </Paper>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h5" fontWeight={700}>Leakage controls</Typography>
          <Typography color="text.secondary" mt={0.75} mb={2}>
            The complete preprocessing and tuning path is frozen with the design. Test-fold data
            may only be used once for outer-fold evaluation.
          </Typography>
          <Stack spacing={1}>
            {[
              ['Preprocessing', configuration.leakage_policy.preprocessing_scope],
              ['Feature selection', configuration.leakage_policy.feature_selection_scope],
              ['Hyperparameter tuning', configuration.leakage_policy.hyperparameter_tuning_scope],
              ['Outer test folds', configuration.leakage_policy.outer_test_fold_role],
            ].map(([label, value]) => (
              <Stack key={label} direction={{ xs: 'column', sm: 'row' }} gap={0.5}>
                <Typography fontWeight={700} sx={{ minWidth: 190 }}>{label}</Typography>
                <Typography color="text.secondary">{value.replaceAll('_', ' ')}</Typography>
              </Stack>
            ))}
          </Stack>
        </Paper>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h5" fontWeight={700}>Outer-fold audit</Typography>
          <Typography color="text.secondary" mt={0.5} mb={2}>
            Every planned split contains both classes and keeps related experimental units apart.
          </Typography>
          <TableContainer sx={{ maxHeight: 360 }}>
            <Table size="small" stickyHeader aria-label="Saved classifier outer-fold audit">
              <TableHead>
                <TableRow>
                  <TableCell>Repeat / fold</TableCell>
                  <TableCell align="right">Train</TableCell>
                  <TableCell align="right">Test</TableCell>
                  <TableCell align="right">Train groups</TableCell>
                  <TableCell align="right">Test groups</TableCell>
                  <TableCell align="right">Overlap</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {validation.fold_plan.map((fold) => (
                  <TableRow key={`${fold.repeat}-${fold.fold}`}>
                    <TableCell>{fold.repeat} / {fold.fold}</TableCell>
                    <TableCell align="right">{fold.training_sample_count}</TableCell>
                    <TableCell align="right">{fold.test_sample_count}</TableCell>
                    <TableCell align="right">{fold.training_group_count}</TableCell>
                    <TableCell align="right">{fold.test_group_count}</TableCell>
                    <TableCell align="right">{fold.group_overlap_count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
        {validation.warnings.map((message) => (
          <Alert key={message} severity="warning">{message}</Alert>
        ))}
        {!latest && (
          <Alert severity="info">
            This validated design is ready to run through grouped repeated nested cross-validation.
          </Alert>
        )}
        {active && (
          <Paper variant="outlined" sx={{ p: 4 }}>
            <LoadingState label={`Classifier ${latest!.state.toLowerCase()}…`} />
            <Typography textAlign="center" color="text.secondary">
              Feature selection, tuning, calibration, and threshold selection are being fitted
              independently inside the applicable training folds.
            </Typography>
          </Paper>
        )}
        {latest?.state === 'FAILED' && (
          <Alert severity="error">{latest.error_summary ?? 'The classifier workflow failed.'}</Alert>
        )}
        {(rerun.isError || cancel.isError) && (
          <Alert severity="error">{(rerun.error ?? cancel.error)?.message}</Alert>
        )}
        {classifierResults.isPending && succeeded && (
          <LoadingState label="Loading out-of-fold classifier results…" />
        )}
        {classifierResults.isError && <ErrorState error={classifierResults.error} />}
        {classifierResults.data?.method === 'multinomial_elastic_net' && (
          <Paper variant="outlined" sx={{ p: 3 }}>
            <Typography variant="h5" fontWeight={700}>Internal multiclass validation results</Typography>
            <Typography color="text.secondary" mt={0.5}>
              Macro metrics use repeated outer-fold predictions across all classes. Probabilities
              are uncalibrated, predictions use maximum class probability, and these estimates are
              not external or clinical validation.
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} mt={2}>
              {[
                [
                  'Macro ROC-AUC',
                  `${classifierResults.data.metrics.macro_roc_auc.toFixed(3)} (${classifierResults.data.confidence_intervals.intervals.macro_roc_auc.lower.toFixed(3)}–${classifierResults.data.confidence_intervals.intervals.macro_roc_auc.upper.toFixed(3)})`,
                ],
                ['Macro F1', classifierResults.data.metrics.macro_f1.toFixed(3)],
                ['Balanced accuracy', classifierResults.data.metrics.balanced_accuracy.toFixed(3)],
                ['Log loss', classifierResults.data.metrics.log_loss.toFixed(3)],
              ].map(([label, value]) => (
                <Paper key={label} variant="outlined" sx={{ p: 2, flex: 1 }}>
                  <Typography variant="overline" color="text.secondary">{label}</Typography>
                  <Typography variant="h5" fontWeight={700}>{value}</Typography>
                </Paper>
              ))}
            </Stack>
            <Alert severity="success" sx={{ mt: 2 }}>
              {classifierResults.data.oof_coverage.observed_prediction_count} of{' '}
              {classifierResults.data.oof_coverage.expected_prediction_count} planned OOF
              predictions are present exactly once per sample per repeat, with zero audited
              experimental-unit overlap.
            </Alert>
            <Alert severity="info" sx={{ mt: 2 }}>
              Full nested-CV label-permutation control ({classifierResults.data.permutation_control.count}{' '}
              permutations): empirical p ={' '}
              {classifierResults.data.permutation_control.empirical_p_value?.toFixed(4) ?? 'not run'}.
            </Alert>
            <Typography variant="h6" fontWeight={700} mt={3}>Confusion matrix</Typography>
            <TableContainer sx={{ mt: 1 }}>
              <Table size="small" aria-label="Multiclass confusion matrix">
                <TableHead><TableRow><TableCell>Observed \ Predicted</TableCell>{classifierResults.data.diagnostics.class_order.map((label) => <TableCell key={label} align="right">{label}</TableCell>)}</TableRow></TableHead>
                <TableBody>{multiclassDiagnostics?.confusion_matrix.map((row, rowIndex) => (
                  <TableRow key={multiclassDiagnostics.class_order[rowIndex]}><TableCell>{multiclassDiagnostics.class_order[rowIndex]}</TableCell>{row.map((value, columnIndex) => <TableCell key={multiclassDiagnostics.class_order[columnIndex]} align="right">{value}</TableCell>)}</TableRow>
                ))}</TableBody>
              </Table>
            </TableContainer>
            <Typography variant="h6" fontWeight={700} mt={3}>Most stable class coefficients</Typography>
            <TableContainer sx={{ maxHeight: 320, mt: 1 }}>
              <Table size="small" stickyHeader aria-label="Multiclass feature stability">
                <TableHead><TableRow><TableCell>Feature</TableCell><TableCell>Class</TableCell><TableCell align="right">Selected</TableCell><TableCell align="right">Nonzero</TableCell><TableCell align="right">Mean coefficient</TableCell></TableRow></TableHead>
                <TableBody>{classifierResults.data.feature_stability.slice(0, 30).map((feature) => (
                  <TableRow key={`${feature.feature_id}-${feature.class_label}`}><TableCell>{feature.feature_id}</TableCell><TableCell>{feature.class_label}</TableCell><TableCell align="right">{(feature.selection_frequency * 100).toFixed(0)}%</TableCell><TableCell align="right">{(feature.nonzero_frequency * 100).toFixed(0)}%</TableCell><TableCell align="right">{feature.mean_coefficient.toFixed(4)}</TableCell></TableRow>
                ))}</TableBody>
              </Table>
            </TableContainer>
            <Alert severity="warning" sx={{ mt: 2 }}>
              The locked multinomial model and inference schema are research artifacts. Evaluate
              them on a compatible untouched cohort before making any generalization claim.
            </Alert>
            {artifacts.data && (
              <Stack direction="row" spacing={2} mt={2} flexWrap="wrap" useFlexGap>
                {artifacts.data.filter((artifact) => artifact.artifact_type.startsWith('classifier_') || ['analysis_report', 'analysis_report_source'].includes(artifact.artifact_type)).map((artifact) => (
                  <Link key={artifact.id} href={artifactDownloadUrl(artifact.id)} underline="hover">
                    <DownloadRoundedIcon fontSize="small" sx={{ verticalAlign: 'middle', mr: 0.5 }} />{artifact.title}
                  </Link>
                ))}
              </Stack>
            )}
          </Paper>
        )}
        {classifierResults.data?.method === 'elastic_net' && (
          <Paper variant="outlined" sx={{ p: 3 }}>
            <Typography variant="h5" fontWeight={700}>Internal validation results</Typography>
            <Typography color="text.secondary" mt={0.5}>
              Metrics use only repeated outer-fold predictions. They are internal validation and
              are not external or clinical performance estimates.
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} mt={2}>
              {[
                [
                  'ROC-AUC',
                  `${classifierResults.data.metrics.roc_auc.toFixed(3)} (${classifierResults.data.confidence_intervals.intervals.roc_auc.lower.toFixed(3)}–${classifierResults.data.confidence_intervals.intervals.roc_auc.upper.toFixed(3)})`,
                ],
                [
                  'PR-AUC',
                  `${classifierResults.data.metrics.pr_auc.toFixed(3)} (${classifierResults.data.confidence_intervals.intervals.pr_auc.lower.toFixed(3)}–${classifierResults.data.confidence_intervals.intervals.pr_auc.upper.toFixed(3)})`,
                ],
                [
                  'Balanced accuracy',
                  classifierResults.data.metrics.balanced_accuracy.toFixed(3),
                ],
                ['Brier score', classifierResults.data.metrics.brier_score.toFixed(3)],
              ].map(([label, value]) => (
                <Paper key={label} variant="outlined" sx={{ p: 2, flex: 1 }}>
                  <Typography variant="overline" color="text.secondary">{label}</Typography>
                  <Typography variant="h5" fontWeight={700}>{value}</Typography>
                </Paper>
              ))}
            </Stack>
            <Alert severity="success" sx={{ mt: 2 }}>
              {classifierResults.data.oof_coverage.observed_prediction_count} of{' '}
              {classifierResults.data.oof_coverage.expected_prediction_count} planned OOF
              predictions are present, exactly once per sample per repeat. Every audited fold has
              zero experimental-unit overlap.
            </Alert>
            <Alert severity="info" sx={{ mt: 2 }}>
              Full nested-CV label-permutation control ({classifierResults.data.permutation_control.count}{' '}
              permutations): empirical p ={' '}
              {classifierResults.data.permutation_control.empirical_p_value?.toFixed(4) ?? 'not run'}.
              Calibration slope is {classifierResults.data.diagnostic_curves.calibration_slope.toFixed(3)}.
            </Alert>
            {classifierDiagnosticImage && (
              <Box
                component="img"
                src={artifactDownloadUrl(classifierDiagnosticImage.id)}
                alt="ROC, precision-recall, and learning curves"
                sx={{ display: 'block', width: '100%', maxWidth: 960, mt: 3 }}
              />
            )}
            <Typography variant="h6" fontWeight={700} mt={3}>Algorithm comparison</Typography>
            <Typography color="text.secondary" mt={0.5}>
              Random forest and histogram gradient boosting use the same outer folds and tune only
              within inner training folds. Elastic net remains the exported primary model.
            </Typography>
            <TableContainer sx={{ mt: 1 }}>
              <Table size="small" aria-label="Classifier algorithm comparison">
                <TableHead><TableRow><TableCell>Algorithm</TableCell><TableCell>Role</TableCell><TableCell align="right">ROC-AUC</TableCell><TableCell align="right">PR-AUC</TableCell><TableCell align="right">Balanced accuracy</TableCell><TableCell align="right">Brier score</TableCell></TableRow></TableHead>
                <TableBody>{classifierResults.data.model_comparisons.map((comparison) => (
                  <TableRow key={comparison.method}><TableCell>{comparison.method.replaceAll('_', ' ')}</TableCell><TableCell>{comparison.role === 'primary_locked_model' ? 'Primary locked model' : 'Comparison only'}</TableCell><TableCell align="right">{comparison.metrics.roc_auc.toFixed(3)}</TableCell><TableCell align="right">{comparison.metrics.pr_auc.toFixed(3)}</TableCell><TableCell align="right">{comparison.metrics.balanced_accuracy.toFixed(3)}</TableCell><TableCell align="right">{comparison.metrics.brier_score.toFixed(3)}</TableCell></TableRow>
                ))}</TableBody>
              </Table>
            </TableContainer>
            <Typography variant="h6" fontWeight={700} mt={3}>Performance by repeat</Typography>
            <TableContainer sx={{ mt: 1 }}>
              <Table size="small" aria-label="Classifier metrics by repeat">
                <TableHead><TableRow><TableCell>Repeat</TableCell><TableCell align="right">ROC-AUC</TableCell><TableCell align="right">PR-AUC</TableCell><TableCell align="right">Balanced accuracy</TableCell><TableCell align="right">Brier score</TableCell></TableRow></TableHead>
                <TableBody>{classifierResults.data.repeat_metrics.map((repeat) => (
                  <TableRow key={repeat.repeat}><TableCell>{repeat.repeat}</TableCell><TableCell align="right">{repeat.roc_auc.toFixed(3)}</TableCell><TableCell align="right">{repeat.pr_auc.toFixed(3)}</TableCell><TableCell align="right">{repeat.balanced_accuracy.toFixed(3)}</TableCell><TableCell align="right">{repeat.brier_score.toFixed(3)}</TableCell></TableRow>
                ))}</TableBody>
              </Table>
            </TableContainer>
            <Typography variant="h6" fontWeight={700} mt={3}>Most stable coefficients</Typography>
            <TableContainer sx={{ maxHeight: 320, mt: 1 }}>
              <Table size="small" stickyHeader aria-label="Classifier feature stability">
                <TableHead><TableRow><TableCell>Feature</TableCell><TableCell align="right">Selected</TableCell><TableCell align="right">Nonzero</TableCell><TableCell align="right">Mean coefficient</TableCell></TableRow></TableHead>
                <TableBody>{classifierResults.data.feature_stability.slice(0, 25).map((feature) => (
                  <TableRow key={feature.feature_id}><TableCell>{feature.feature_id}</TableCell><TableCell align="right">{(feature.selection_frequency * 100).toFixed(0)}%</TableCell><TableCell align="right">{(feature.nonzero_frequency * 100).toFixed(0)}%</TableCell><TableCell align="right">{feature.mean_coefficient.toFixed(4)}</TableCell></TableRow>
                ))}</TableBody>
              </Table>
            </TableContainer>
            <Alert severity="warning" sx={{ mt: 2 }}>
              A locked research model, model card, inference schema, and prediction template are
              available below. This lock occurs only after internal validation; performance still
              requires an untouched compatible external cohort.
            </Alert>
            {artifacts.data && (
              <Stack direction="row" spacing={2} mt={2} flexWrap="wrap" useFlexGap>
                {artifacts.data.filter((artifact) => artifact.artifact_type.startsWith('classifier_') || ['analysis_report', 'analysis_report_source'].includes(artifact.artifact_type)).map((artifact) => (
                  <Link key={artifact.id} href={artifactDownloadUrl(artifact.id)} underline="hover">
                    <DownloadRoundedIcon fontSize="small" sx={{ verticalAlign: 'middle', mr: 0.5 }} />{artifact.title}
                  </Link>
                ))}
              </Stack>
            )}
          </Paper>
        )}
      </Stack>
    )
  }
  if (configuration.analysis_type === 'deconvolution') {
    const active = Boolean(latest && activeStates.has(latest.state))
    const isExternalImport = configuration.method === 'cibersortx_external'
    const canRun = configuration.execution_available && !active && !rerun.isPending
    return (
      <Stack spacing={3}>
        <Link
          component={RouterLink}
          to={`/prepared-datasets/${analysis.data.prepared_dataset_id}`}
          underline="hover"
          sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, width: 'fit-content' }}
        >
          <ArrowBackRoundedIcon fontSize="small" /> Expression Bundle v{prepared.data?.version ?? '…'}
        </Link>
        <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" gap={2}>
          <Box>
            <Typography variant="overline" color="secondary.main" fontWeight={750}>
              {isExternalImport
                ? 'Cell-type deconvolution · audited external result'
                : 'Cell-type deconvolution · validated input contract'}
            </Typography>
            <Typography variant="h3" fontWeight={750}>{analysis.data.name}</Typography>
            <Typography color="text.secondary" mt={1}>
              {configuration.method_spec.display_name} · {configuration.assay} ·{' '}
              {configuration.parameters.reference_profile}
            </Typography>
          </Box>
          {isExternalImport ? (
            <Chip label="External import" color="info" />
          ) : active && latest ? (
            <Button
              variant="outlined"
              color="error"
              startIcon={<StopCircleRoundedIcon />}
              onClick={() => cancel.mutate(latest.id)}
              disabled={cancel.isPending || latest.state === 'CANCELLING'}
            >
              {latest.state === 'CANCELLING' ? 'Stopping…' : 'Stop analysis'}
            </Button>
          ) : (
            <Button
              variant="contained"
              startIcon={latest ? <ReplayRoundedIcon /> : <PlayArrowRoundedIcon />}
              onClick={() => rerun.mutate()}
              disabled={!canRun}
            >
              {configuration.execution_available
                ? (rerun.isPending ? 'Queueing…' : latest ? 'Run again' : `Run ${configuration.method_spec.display_name}`)
                : 'Runner unavailable'}
            </Button>
          )}
        </Stack>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          {[
            ['Output type', configuration.result_type.replace('_', ' ')],
            ['Quantity', configuration.method_spec.quantity_label],
            ['Minimum overlap', `${(configuration.parameters.minimum_gene_overlap * 100).toFixed(0)}%`],
            ['Registry', configuration.method_registry_version],
          ].map(([label, value]) => (
            <Paper key={label} variant="outlined" sx={{ p: 2, flex: 1 }}>
              <Typography variant="overline" color="text.secondary">{label}</Typography>
              <Typography variant="h6" fontWeight={700}>{value}</Typography>
            </Paper>
          ))}
        </Stack>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Stack spacing={1.5}>
            <Stack direction="row" spacing={1} flexWrap="wrap">
              <Chip
                color={configuration.result_type === 'cell_fraction' ? 'primary' : 'warning'}
                label={configuration.result_type === 'cell_fraction'
                  ? 'Cell fractions'
                  : 'Enrichment scores · not percentages'}
              />
              <Chip label={`${configuration.input_assay_descriptor.scale} scale`} />
              <Chip label={configuration.method_spec.composition_constraint.replaceAll('_', ' ')} />
            </Stack>
            <Typography>{configuration.method_spec.interpretation}</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: 'anywhere' }}>
              Assay SHA-256: <code>{configuration.input_assay_descriptor.sha256}</code><br />
              Method registry SHA-256: <code>{configuration.method_registry_sha256}</code>
            </Typography>
            <Link
              href={configuration.method_spec.source_url}
              target="_blank"
              rel="noreferrer"
              underline="hover"
              sx={{ width: 'fit-content' }}
            >
              Method documentation
            </Link>
          </Stack>
        </Paper>
        {isExternalImport ? (
          <Alert severity="success">
            This result was imported rather than executed by TranscriptForge. Its original source,
            source checksum, signature checksum, external runtime, mode, and input-assay link are
            frozen with the result.
          </Alert>
        ) : configuration.execution_available ? (
          <Alert severity="success">
            This design can run in the pinned scientific container. Every run verifies the package,
            reference checksum, assay contract, and effective gene overlap before estimating results.
          </Alert>
        ) : (
          <Alert severity="info">
            This design is saved but cannot run in the default installation. See the method source
            and licensing status above.
          </Alert>
        )}
        {latest && (
          <Alert severity={latest.state === 'FAILED' ? 'error' : latest.state === 'SUCCEEDED' ? 'success' : 'info'}>
            Latest run: {latest.state.replaceAll('_', ' ').toLowerCase()}.
            {latest.error_summary ? ` ${latest.error_summary}` : ''}
          </Alert>
        )}
        {(rerun.isError || cancel.isError) && (
          <Alert severity="error">{(rerun.error ?? cancel.error)?.message}</Alert>
        )}
        {deconvolutionResults.isPending && succeeded && <LoadingState label="Loading cell-population results…" />}
        {deconvolutionResults.isError && <ErrorState error={deconvolutionResults.error} />}
        {deconvolutionResults.data && (
          <DeconvolutionResultPanel
            result={deconvolutionResults.data}
            artifacts={artifacts.data ?? []}
          />
        )}
        {deconvolutionComparison.isPending && succeeded && (
          <LoadingState label="Finding compatible deconvolution results…" />
        )}
        {deconvolutionComparison.isError && <ErrorState error={deconvolutionComparison.error} />}
        {deconvolutionComparison.data && (
          <DeconvolutionComparisonPanel
            comparison={deconvolutionComparison.data}
            currentRunId={latest?.id}
          />
        )}
        <Alert severity="warning">
          Research use only. Cell fractions and enrichment scores have different mathematical
          meanings and must never be relabeled or normalized into one another.
        </Alert>
      </Stack>
    )
  }
  if (configuration.analysis_type === 'signature') {
    const methodLabels = {
      mean_expression: 'Mean expression',
      mean_z_score: 'Mean z-score',
      weighted_linear: 'Weighted linear score',
      rank_based: 'Rank-based score',
      gsva: 'GSVA',
      ssgsea: 'ssGSEA',
    }
    return (
      <Stack spacing={3}>
        <Link
          component={RouterLink}
          to={`/prepared-datasets/${analysis.data.prepared_dataset_id}`}
          underline="hover"
          sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, width: 'fit-content' }}
        >
          <ArrowBackRoundedIcon fontSize="small" /> Expression Bundle v{prepared.data?.version ?? '…'}
        </Link>
        <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" gap={2}>
          <Box>
            <Typography variant="overline" color="secondary.main" fontWeight={750}>
              Signature analysis · {methodLabels[configuration.method]}
            </Typography>
            <Typography variant="h3" fontWeight={750}>{analysis.data.name}</Typography>
            <Typography color="text.secondary" mt={1}>
              {configuration.assay} · mapping coverage{' '}
              {(configuration.mapping_coverage * 100).toFixed(1)}%
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} alignItems="center">
            {latest && <RunStateChip run={latest} />}
            {latest && activeStates.has(latest.state) && (
              <CancelRunButton run={latest} pending={cancel.isPending} onCancel={cancel.mutate} />
            )}
            <Button
              variant={latest ? 'outlined' : 'contained'}
              startIcon={<ReplayRoundedIcon />}
              onClick={() => rerun.mutate()}
              disabled={rerun.isPending || Boolean(latest && activeStates.has(latest.state))}
            >
              {latest ? 'Run again' : 'Run signature scoring'}
            </Button>
          </Stack>
        </Stack>
        {!latest && <Alert severity="info">This signature analysis has not been run yet.</Alert>}
        {latest && activeStates.has(latest.state) && (
          <Paper variant="outlined" sx={{ p: 4 }}>
            <LoadingState label={`Signature scoring ${latest.state.toLowerCase()}…`} />
            <Typography textAlign="center" color="text.secondary">
              This page updates automatically while Nextflow scores the frozen mapping.
            </Typography>
          </Paper>
        )}
        {latest?.state === 'FAILED' && (
          <Alert severity="error">
            {latest.error_summary ?? 'The signature-scoring workflow failed.'}
          </Alert>
        )}
        {signatureScores.isError && <ErrorState error={signatureScores.error} />}
        {signatureScores.data && <SignatureScoreResults summary={signatureScores.data} />}
        {artifacts.data && (
          <Paper variant="outlined" sx={{ p: 3 }}>
            <Typography variant="h5" fontWeight={700}>Results and provenance</Typography>
            <Stack direction="row" spacing={2} mt={2} flexWrap="wrap">
              {artifacts.data.filter((artifact) => [
                'signature_scores', 'signature_scores_table', 'signature_scored_features',
                'signature_scores_svg', 'signature_associations_table',
                'signature_associations_svg', 'analysis_report', 'analysis_report_source',
                'nextflow_report', 'nextflow_trace',
              ].includes(artifact.artifact_type)).map((artifact) => (
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
        )}
        <Alert severity="info">
          Research use only. Do not compare raw signature-score magnitudes across RNA-seq,
          microarray, cohorts, or preprocessing pipelines. Compare prespecified within-dataset
          direction, ranking, association, or standardized effects, with mapping coverage and final
          scored features attached. Scores are not clinically validated.
        </Alert>
      </Stack>
    )
  }
  if (configuration.analysis_type === 'differential_expression') {
    return (
      <Stack spacing={3}>
        <Link
          component={RouterLink}
          to={`/prepared-datasets/${analysis.data.prepared_dataset_id}`}
          underline="hover"
          sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, width: 'fit-content' }}
        >
          <ArrowBackRoundedIcon fontSize="small" /> Expression Bundle v{prepared.data?.version ?? '…'}
        </Link>
        <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" gap={2}>
          <Box>
            <Typography variant="overline" color="secondary.main" fontWeight={750}>
              Differential expression · validated design
            </Typography>
            <Typography variant="h3" fontWeight={750}>{analysis.data.name}</Typography>
            <Typography color="text.secondary" mt={1}>
              {configuration.assay} · {configuration.method}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} alignItems="center">
            {latest && <RunStateChip run={latest} />}
            {latest && activeStates.has(latest.state) && (
              <CancelRunButton run={latest} pending={cancel.isPending} onCancel={cancel.mutate} />
            )}
            <Button
              variant={latest ? 'outlined' : 'contained'}
              startIcon={latest ? <ReplayRoundedIcon /> : <PlayArrowRoundedIcon />}
              onClick={() => rerun.mutate()}
              disabled={rerun.isPending || Boolean(latest && activeStates.has(latest.state))}
            >
              {latest ? 'Run again' : 'Run differential expression'}
            </Button>
          </Stack>
        </Stack>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          {[
            ['Samples', configuration.design_validation.sample_count],
            ['Model rank', `${configuration.design_validation.design_matrix_rank}/${configuration.design_validation.design_matrix_columns.length}`],
            ['FDR', configuration.parameters.fdr_threshold],
            ['Absolute log2 FC', configuration.parameters.absolute_log2_fold_change],
          ].map(([label, value]) => (
            <Paper key={label} variant="outlined" sx={{ p: 2, flex: 1 }}>
              <Typography variant="overline" color="text.secondary">{label}</Typography>
              <Typography variant="h6" fontWeight={700}>{value}</Typography>
            </Paper>
          ))}
        </Stack>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h5" fontWeight={700}>Model and contrast</Typography>
          <Typography variant="overline" color="text.secondary" display="block" mt={2}>
            Formula
          </Typography>
          <Typography component="code" sx={{ fontFamily: 'monospace', fontSize: '1.1rem' }}>
            {configuration.design_formula}
          </Typography>
          <Typography mt={2}><strong>Contrast:</strong> {configuration.contrast_label}</Typography>
          <Stack direction="row" spacing={1} mt={2} flexWrap="wrap">
            {Object.entries(configuration.design_validation.contrast_counts).map(([level, count]) => (
              <Chip key={level} label={`${level}: ${count} samples`} />
            ))}
          </Stack>
        </Paper>
        {!latest && (
          <Alert severity="info">
            Design saved. Review the frozen model above, then select “Run differential expression”
            to start the workflow.
          </Alert>
        )}
        {latest && activeStates.has(latest.state) && (
          <Paper variant="outlined" sx={{ p: 4 }}>
            <LoadingState label={`Differential expression ${latest.state.toLowerCase()}…`} />
            <Typography textAlign="center" color="text.secondary">
              This page updates automatically while Nextflow and {configuration.method} execute the frozen request.
            </Typography>
          </Paper>
        )}
        {latest?.state === 'FAILED' && (
          <Alert severity="error">{latest.error_summary ?? 'The differential-expression workflow failed.'}</Alert>
        )}
        {volcano.data && (
          <DifferentialExpressionScatter
            plot={volcano.data}
            title="Volcano plot"
            onSelectFeature={setSelectedFeature}
          />
        )}
        {maPlot.data && (
          <DifferentialExpressionScatter
            plot={maPlot.data}
            title="MA plot"
            onSelectFeature={setSelectedFeature}
          />
        )}
        {succeeded && latest && (
          <DifferentialExpressionResultsExplorer
            runId={latest.id}
            onSelectFeature={setSelectedFeature}
          />
        )}
        {pValueDistribution.data && <PValueDistributionChart distribution={pValueDistribution.data} />}
        {expressionHeatmap.data && <DifferentialExpressionHeatmap heatmap={expressionHeatmap.data} />}
        {enrichment.data && <EnrichmentPanel summary={enrichment.data} />}
        {enrichment.isError && <ErrorState error={enrichment.error} />}
        {manifest.data && (
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            {manifest.data.summary_metrics.map((metric) => (
              <Paper variant="outlined" sx={{ p: 2, flex: 1 }} key={metric.label}>
                <Typography variant="overline" color="text.secondary">{metric.label}</Typography>
                <Typography variant="h6" fontWeight={700}>{String(metric.value)}</Typography>
              </Paper>
            ))}
          </Stack>
        )}
        {manifest.data?.warnings.map((warning) => (
          <Alert severity="warning" key={warning}>{warning}</Alert>
        ))}
        {artifacts.data && (
          <Paper variant="outlined" sx={{ p: 3 }}>
            <Typography variant="h5" fontWeight={700}>Results and provenance</Typography>
            <Stack direction="row" spacing={2} mt={2} flexWrap="wrap">
              {artifacts.data.filter((artifact) => [
                'differential_expression_results', 'significant_results', 'normalized_expression',
                'design_matrix',
                'contrast_definition', 'method_diagnostics', 'volcano_plot_svg', 'ma_plot_svg',
                'p_value_distribution_svg', 'expression_heatmap_svg',
                'enrichment_summary', 'ranked_enrichment', 'over_representation',
                'enrichment_plot_svg',
                'r_session_info', 'analysis_report', 'analysis_report_source', 'nextflow_report',
                'nextflow_trace',
              ].includes(artifact.artifact_type)).map((artifact) => (
                <Link key={artifact.id} href={artifactDownloadUrl(artifact.id)} underline="hover" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}>
                  <DownloadRoundedIcon fontSize="small" /> {artifact.title}
                </Link>
              ))}
            </Stack>
          </Paper>
        )}
        <Alert severity="info">
          Research use only. Interpret differential-expression results with sample QC,
          study design, effect sizes, and uncertainty; outputs are not clinically validated.
        </Alert>
        {latest && (
          <GeneDetailDrawer
            runId={latest.id}
            featureId={selectedFeature}
            onClose={() => setSelectedFeature(null)}
          />
        )}
      </Stack>
    )
  }
  const methodLabels = {
    pca: 'PCA',
    hierarchical_clustering: 'Hierarchical clustering',
    umap: 'UMAP',
    tsne: 't-SNE',
  }
  return (
    <Stack spacing={3}>
      <Link
        component={RouterLink}
        to={`/prepared-datasets/${analysis.data.prepared_dataset_id}`}
        underline="hover"
        sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, width: 'fit-content' }}
      >
        <ArrowBackRoundedIcon fontSize="small" /> Expression Bundle v{prepared.data?.version ?? '…'}
      </Link>
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" gap={2}>
        <Box>
          <Typography variant="overline" color="secondary.main" fontWeight={750}>
            Dimension reduction · {methodLabels[configuration.method]}
          </Typography>
          <Typography variant="h3" fontWeight={750}>{analysis.data.name}</Typography>
          <Typography color="text.secondary" mt={1}>
            {configuration.assay} · seed {configuration.random_seed}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center">
          {latest && <RunStateChip run={latest} />}
          {latest && activeStates.has(latest.state) && (
            <CancelRunButton run={latest} pending={cancel.isPending} onCancel={cancel.mutate} />
          )}
          <Button
            variant={latest ? 'outlined' : 'contained'}
            startIcon={latest ? <ReplayRoundedIcon /> : <PlayArrowRoundedIcon />}
            onClick={() => rerun.mutate()}
            disabled={rerun.isPending || Boolean(latest && activeStates.has(latest.state))}
          >
            {latest ? 'Run again' : 'Run analysis'}
          </Button>
        </Stack>
      </Stack>

      {!latest && <Alert severity="info">This saved analysis has not been run yet.</Alert>}
      {latest && activeStates.has(latest.state) && (
        <Paper variant="outlined" sx={{ p: 4 }}>
          <LoadingState label={`Analysis ${latest.state.toLowerCase()}…`} />
          <Typography textAlign="center" color="text.secondary">
            This page updates automatically while Nextflow executes the frozen request.
          </Typography>
        </Paper>
      )}
      {latest?.state === 'FAILED' && (
        <Alert severity="error">{latest.error_summary ?? 'The analysis workflow failed.'}</Alert>
      )}
      {plot.data && (
        <CoordinateScatter
          axes={plot.data.axes.map((axis) => ({
            name: axis.component,
            explainedVarianceRatio: axis.explained_variance_ratio,
          }))}
          points={plot.data.points}
          methodLabel="PCA"
        />
      )}
      {embedding.data && <EmbeddingResult plot={embedding.data} />}
      {dendrogram.data && <DendrogramChart plot={dendrogram.data} />}
      {heatmap.data && <CorrelationChart heatmap={heatmap.data} />}
      {variance.data && <VarianceChart components={variance.data.components} />}

      {manifest.data && (
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          {manifest.data.summary_metrics.map((metric) => (
            <Paper variant="outlined" sx={{ p: 2, flex: 1 }} key={metric.label}>
              <Typography variant="overline" color="text.secondary">{metric.label}</Typography>
              <Typography variant="h6" fontWeight={700}>{String(metric.value)}</Typography>
            </Paper>
          ))}
        </Stack>
      )}

      {artifacts.data && (
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h5" fontWeight={700}>Results and provenance</Typography>
          <Stack direction="row" spacing={2} mt={2} flexWrap="wrap">
            {artifacts.data
              .filter((artifact) => [
                'coordinates',
                'pca_coordinates',
                'pca_loadings',
                'explained_variance',
                'pca_variance',
                'cluster_assignments',
                'linkage_matrix',
                'pca_plot_svg',
                'variance_plot_svg',
                'embedding_plot_svg',
                'dendrogram_plot_svg',
                'correlation_heatmap_svg',
                'analysis_report',
                'analysis_report_source',
                'nextflow_report',
                'nextflow_trace',
              ].includes(artifact.artifact_type))
              .map((artifact) => (
                <Link key={artifact.id} href={artifactDownloadUrl(artifact.id)} underline="hover" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}>
                  <DownloadRoundedIcon fontSize="small" /> {artifact.title}
                </Link>
              ))}
          </Stack>
        </Paper>
      )}
      <Alert severity="info">Research use only. Interpret exploratory structure with sample QC and study design context.</Alert>
    </Stack>
  )
}

function DeconvolutionResultPanel({
  result,
  artifacts,
}: {
  result: DeconvolutionResults
  artifacts: Artifact[]
}) {
  const values = new Map(
    result.estimates.map((item) => [`${item.sample_id}\u0000${item.cell_type_id}`, item.value]),
  )
  const isFraction = result.result_type === 'cell_fraction'
  const variablePopulations = result.cell_types
    .map((cellType) => {
      const populationValues = result.sample_ids.map(
        (sampleId) => values.get(`${sampleId}\u0000${cellType.id}`) ?? 0,
      )
      const mean = populationValues.reduce((sum, value) => sum + value, 0) / populationValues.length
      const variance = populationValues.length > 1
        ? populationValues.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (populationValues.length - 1)
        : 0
      return { ...cellType, values: populationValues, mean, deviation: Math.sqrt(variance), variance }
    })
    .sort((left, right) => right.variance - left.variance)
    .slice(0, 20)
  const resultArtifacts = artifacts.filter((artifact) => [
    'deconvolution_results',
    'deconvolution_estimates',
    'deconvolution_reference_overlap',
    'deconvolution_fractions_svg',
    'deconvolution_enrichment_svg',
    'cibersortx_source',
    'external_import_provenance',
    'analysis_report',
    'analysis_report_source',
    'r_session_info',
    'nextflow_report',
    'nextflow_trace',
  ].includes(artifact.artifact_type))
  return (
    <Stack spacing={3}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        {[
          ['Samples', result.sample_ids.length],
          ['Populations', result.cell_types.length],
          ['Reference overlap', `${(result.input_validation.overlap_fraction * 100).toFixed(1)}%`],
          ['Reference', result.reference.version],
        ].map(([label, value]) => (
          <Paper key={label} variant="outlined" sx={{ p: 2, flex: 1 }}>
            <Typography variant="overline" color="text.secondary">{label}</Typography>
            <Typography variant="h6" fontWeight={700}>{value}</Typography>
          </Paper>
        ))}
      </Stack>
      {isFraction ? (
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h5" fontWeight={700}>
            {result.method === 'cibersortx_external'
              ? 'Imported relative cell fractions'
              : 'Estimated cell fractions'}
          </Typography>
          <Typography color="text.secondary" mt={0.5} mb={2.5}>
            {result.method === 'cibersortx_external'
              ? 'Each bar is an externally estimated CIBERSORTx relative-mode composition. TranscriptForge validated the table but did not reproduce the computation.'
              : 'Each bar sums to one and includes the method’s Other / uncharacterized compartment.'}
          </Typography>
          <Stack spacing={2}>
            {result.sample_ids.map((sampleId) => (
              <Box key={sampleId}>
                <Typography variant="body2" fontWeight={700} mb={0.5}>{sampleId}</Typography>
                <Stack
                  direction="row"
                  sx={{ height: 26, borderRadius: 1, overflow: 'hidden', bgcolor: 'action.hover' }}
                  aria-label={`${sampleId} cell fractions`}
                >
                  {result.cell_types.map((cellType, index) => {
                    const value = values.get(`${sampleId}\u0000${cellType.id}`) ?? 0
                    return (
                      <Box
                        key={cellType.id}
                        title={`${cellType.label}: ${(value * 100).toFixed(1)}%`}
                        sx={{ width: `${value * 100}%`, bgcolor: colors[index % colors.length], minWidth: value > 0 ? 1 : 0 }}
                      />
                    )
                  })}
                </Stack>
              </Box>
            ))}
            <Stack direction="row" gap={1.5} flexWrap="wrap">
              {result.cell_types.map((cellType, index) => (
                <Stack key={cellType.id} direction="row" spacing={0.5} alignItems="center">
                  <Box sx={{ width: 10, height: 10, borderRadius: '2px', bgcolor: colors[index % colors.length] }} />
                  <Typography variant="caption">{cellType.label}</Typography>
                </Stack>
              ))}
            </Stack>
          </Stack>
        </Paper>
      ) : (
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h5" fontWeight={700}>Cell-population enrichment patterns</Typography>
          <Typography color="text.secondary" mt={0.5} mb={2.5}>
            The 20 most variable populations are shown. Color is a within-population z-score used
            only to reveal between-sample patterns; every cell also shows the untransformed score.
          </Typography>
          <TableContainer sx={{ maxHeight: 720 }}>
            <Table size="small" stickyHeader aria-label={`${result.method} enrichment scores`}>
              <TableHead>
                <TableRow>
                  <TableCell>Population</TableCell>
                  {result.sample_ids.map((sampleId) => <TableCell key={sampleId} align="right">{sampleId}</TableCell>)}
                </TableRow>
              </TableHead>
              <TableBody>
                {variablePopulations.map((population) => (
                  <TableRow key={population.id}>
                    <TableCell component="th" scope="row" sx={{ minWidth: 180 }}>{population.label}</TableCell>
                    {population.values.map((value, index) => {
                      const zScore = population.deviation > 0 ? (value - population.mean) / population.deviation : 0
                      const strength = Math.min(0.78, 0.12 + Math.abs(zScore) * 0.22)
                      return (
                        <TableCell
                          key={result.sample_ids[index]}
                          align="right"
                          title={`Within-population z-score: ${zScore.toFixed(2)}`}
                          sx={{
                            bgcolor: zScore >= 0
                              ? `rgba(105, 65, 198, ${strength})`
                              : `rgba(30, 138, 146, ${strength})`,
                            color: Math.abs(zScore) > 1.25 ? 'common.white' : 'text.primary',
                            fontVariantNumeric: 'tabular-nums',
                          }}
                        >
                          {value.toFixed(4)}
                        </TableCell>
                      )
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          <Alert severity="info" sx={{ mt: 2 }}>
            Scores are not percentages and do not sum to one. Compare a population across samples;
            do not compare score magnitude between different populations within one sample.
          </Alert>
        </Paper>
      )}
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography variant="h5" fontWeight={700}>{isFraction ? 'Fraction table' : 'Complete enrichment-score table'}</Typography>
        <TableContainer sx={{ mt: 2 }}>
          <Table size="small" aria-label={`${result.method} cell-population estimates`}>
            <TableHead>
              <TableRow>
                <TableCell>Sample</TableCell>
                {result.cell_types.map((cellType) => (
                  <TableCell key={cellType.id} align="right">{cellType.label}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {result.sample_ids.map((sampleId) => (
                <TableRow key={sampleId}>
                  <TableCell component="th" scope="row">{sampleId}</TableCell>
                  {result.cell_types.map((cellType) => (
                    <TableCell key={cellType.id} align="right">
                      {isFraction
                        ? `${((values.get(`${sampleId}\u0000${cellType.id}`) ?? 0) * 100).toFixed(1)}%`
                        : (values.get(`${sampleId}\u0000${cellType.id}`) ?? 0).toFixed(4)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
      {result.external_import && (
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h5" fontWeight={700}>External execution provenance</Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap mt={1.5}>
            <Chip label={`Mode: ${result.external_import.mode}`} />
            <Chip label={`Batch correction: ${result.external_import.batch_correction}`} />
            <Chip label={`${result.external_import.permutations} permutations`} />
            <Chip label={`Runtime: ${result.external_import.runtime.version}`} />
          </Stack>
          <Typography variant="body2" mt={2} sx={{ overflowWrap: 'anywhere' }}>
            <strong>Signature:</strong> {result.external_import.signature.name}{' '}
            {result.external_import.signature.version} · {result.external_import.signature.gene_count}{' '}
            genes<br />
            <strong>External run:</strong> {result.external_import.runtime.external_run_id} ·{' '}
            {new Date(result.external_import.runtime.executed_at).toLocaleString()}<br />
            <strong>Source:</strong> {result.external_import.source_filename} · SHA-256{' '}
            <code>{result.external_import.source_sha256}</code><br />
            <strong>Signature SHA-256:</strong>{' '}
            <code>{result.external_import.signature.sha256}</code>
          </Typography>
          <Alert severity="info" sx={{ mt: 2 }}>
            Provenance is user-declared and checksum-frozen. TranscriptForge did not receive
            credentials, execute CIBERSORTx, or independently verify the external runtime.
          </Alert>
        </Paper>
      )}
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography variant="h5" fontWeight={700}>Results and provenance</Typography>
        <Typography variant="body2" color="text.secondary" mt={0.75} sx={{ overflowWrap: 'anywhere' }}>
          {Object.entries(result.software.packages).map(([name, version]) => `${name} ${version}`).join(' · ')}
          {' '}· reference SHA-256 {result.reference.sha256}
        </Typography>
        <Stack direction="row" spacing={2} mt={2} flexWrap="wrap">
          {resultArtifacts.map((artifact) => (
            <Link key={artifact.id} href={artifactDownloadUrl(artifact.id)} underline="hover" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}>
              <DownloadRoundedIcon fontSize="small" /> {artifact.title}
            </Link>
          ))}
        </Stack>
      </Paper>
      {result.warnings.map((warning) => <Alert key={warning} severity="warning">{warning}</Alert>)}
    </Stack>
  )
}

function DeconvolutionComparisonPanel({
  comparison,
  currentRunId,
}: {
  comparison: DeconvolutionComparison
  currentRunId?: string
}) {
  const sectionTitle = (resultType: 'cell_fraction' | 'enrichment_score') =>
    resultType === 'cell_fraction' ? 'Fraction-estimate comparison' : 'Enrichment-pattern comparison'
  return (
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
      <Stack spacing={2.5}>
        <Box>
          <Typography variant="overline" color="secondary.main" fontWeight={750}>
            Same expression bundle
          </Typography>
          <Typography variant="h5" fontWeight={700}>Cross-method comparison</Typography>
          <Typography color="text.secondary" mt={0.5}>{comparison.interpretation}</Typography>
        </Box>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Chip label={`${comparison.latest_successful_run_count} latest successful runs`} />
          <Chip label={`${comparison.sections.length} compatible result groups`} />
          {comparison.exclusions.length > 0 && (
            <Chip color="warning" label={`${comparison.exclusions.length} excluded`} />
          )}
        </Stack>
        {comparison.sections.length === 0 && (
          <Alert severity="info">
            Run another deconvolution method on this expression bundle to create a compatible
            comparison. Fraction estimates and enrichment scores remain deliberately separate.
          </Alert>
        )}
        {comparison.sections.map((section) => (
          <Paper key={section.id} variant="outlined" sx={{ p: { xs: 2, md: 2.5 }, bgcolor: 'background.default' }}>
            <Stack spacing={2}>
              <Box>
                <Typography variant="h6" fontWeight={700}>{sectionTitle(section.result_type)}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {section.result_type === 'cell_fraction'
                    ? 'Compare the same named population across samples; composition constraints remain visible.'
                    : 'Pearson correlations compare within-population sample patterns. Raw score magnitudes are not compared across methods.'}
                </Typography>
              </Box>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <Chip size="small" label={`${section.runs.length} methods`} />
                <Chip size="small" label={`${section.sample_ids.length} shared samples`} />
                <Chip size="small" label={`${section.shared_cell_types.length} exact shared populations`} />
                <Chip size="small" label={`${section.assay.name} · ${section.assay.scale}`} />
              </Stack>
              <TableContainer>
                <Table size="small" aria-label={`${section.result_type} compatible method runs`}>
                  <TableHead>
                    <TableRow>
                      <TableCell>Method and analysis</TableCell>
                      <TableCell>Reference</TableCell>
                      <TableCell>Composition</TableCell>
                      <TableCell align="right">Reference overlap</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {section.runs.map((run) => (
                      <TableRow key={run.run_id}>
                        <TableCell>
                          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                            <Link component={RouterLink} to={`/analyses/${run.analysis_id}`} underline="hover">
                              {run.display_name} · {run.analysis_name}
                            </Link>
                            {run.run_id === currentRunId && <Chip size="small" color="primary" label="Current" />}
                          </Stack>
                        </TableCell>
                        <TableCell>{run.reference.id} · {run.reference.version}</TableCell>
                        <TableCell>{run.composition_constraint.replaceAll('_', ' ')}</TableCell>
                        <TableCell align="right">{(run.reference_overlap_fraction * 100).toFixed(1)}%</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              {section.correlations.length > 0 ? (
                <TableContainer>
                  <Table size="small" aria-label={`${section.result_type} cross-method concordance`}>
                    <TableHead>
                      <TableRow>
                        <TableCell>Exact shared population</TableCell>
                        <TableCell>Method pair</TableCell>
                        <TableCell align="right">Samples</TableCell>
                        <TableCell align="right">Pearson r</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {section.correlations.map((correlation) => (
                        <TableRow key={`${correlation.left_run_id}-${correlation.right_run_id}-${correlation.cell_type_id}`}>
                          <TableCell>{correlation.cell_type_label}</TableCell>
                          <TableCell>{correlation.left_method} ↔ {correlation.right_method}</TableCell>
                          <TableCell align="right">{correlation.sample_count}</TableCell>
                          <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums', fontWeight: 700 }}>
                            {correlation.pearson_correlation.toFixed(3)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Alert severity="info">
                  At least two compatible methods, three samples, and a variable exact-match
                  population are required for a correlation.
                </Alert>
              )}
              {section.warnings.map((warning) => (
                <Alert key={warning} severity="warning">{warning}</Alert>
              ))}
            </Stack>
          </Paper>
        ))}
        {comparison.exclusions.map((exclusion) => (
          <Alert key={`${exclusion.analysis_id}-${exclusion.run_id}`} severity="warning">
            <strong>{exclusion.analysis_name}</strong> was excluded: {exclusion.reason}
          </Alert>
        ))}
      </Stack>
    </Paper>
  )
}

function RunStateChip({ run }: { run: Run }) {
  const color = run.state === 'SUCCEEDED' ? 'success' : run.state === 'FAILED' ? 'error' : 'warning'
  return <Chip label={run.state} color={color} />
}

function CancelRunButton({
  run,
  pending,
  onCancel,
}: {
  run: Run
  pending: boolean
  onCancel: (runId: string) => void
}) {
  return (
    <Button
      color="error"
      variant="outlined"
      startIcon={<StopCircleRoundedIcon />}
      disabled={pending || run.state === 'CANCELLING'}
      onClick={() => onCancel(run.id)}
    >
      {run.state === 'CANCELLING' ? 'Stopping…' : 'Stop run'}
    </Button>
  )
}

function SignatureScoreResults({ summary }: { summary: SignatureScores }) {
  const mapping = summary.signature_mapping
  return (
    <Stack spacing={3}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        {[
          ['Samples', summary.sample_count],
          ['Signature sets', summary.set_count],
          ['Mapping coverage', `${(mapping.mapping_coverage * 100).toFixed(1)}%`],
          ['Mapped / requested', `${mapping.mapped_identifier_count}/${mapping.requested_identifier_count}`],
        ].map(([label, value]) => (
          <Paper key={label} variant="outlined" sx={{ p: 2, flex: 1 }}>
            <Typography variant="overline" color="text.secondary">{label}</Typography>
            <Typography variant="h6" fontWeight={700}>{value}</Typography>
          </Paper>
        ))}
      </Stack>
      <Paper variant="outlined" sx={{ p: 2.5 }}>
        <Typography variant="overline" color="text.secondary">Frozen score definition</Typography>
        <Typography>{summary.formula}</Typography>
        <Typography variant="body2" color="text.secondary" mt={1} sx={{ overflowWrap: 'anywhere' }}>
          Mapping report SHA-256: <code>{mapping.report_sha256}</code><br />
          Expression Bundle SHA-256: <code>{mapping.expression_bundle_sha256}</code><br />
          Runtime: {summary.software.language} {summary.software.language_version}<br />
          Implementation: {summary.software.implementation}<br />
          Packages: {Object.entries(summary.software.packages)
            .map(([name, version]) => `${name} ${version}`).join(' · ')}
        </Typography>
      </Paper>
      {summary.warnings.map((warning) => (
        <Alert severity="warning" key={warning}>{warning}</Alert>
      ))}
      {summary.phenotype_association && (
        <SignatureAssociationResults summary={summary} />
      )}
      {summary.sets.map((signatureSet) => {
        const range = signatureSet.score_maximum - signatureSet.score_minimum
        return (
          <Paper key={signatureSet.signature_id} variant="outlined" sx={{ p: 3 }}>
            <Stack spacing={2}>
              <div>
                <Typography variant="h5" fontWeight={700}>{signatureSet.name}</Typography>
                <Typography color="text.secondary">
                  {signatureSet.scored_feature_count} final features ·{' '}
                  {(signatureSet.mapping_coverage * 100).toFixed(1)}% mapped · score range{' '}
                  {formatNumber(signatureSet.score_minimum)} to{' '}
                  {formatNumber(signatureSet.score_maximum)}
                </Typography>
              </div>
              <Box
                aria-label={`${signatureSet.name} score distribution`}
                sx={{
                  position: 'relative', height: 56, bgcolor: 'grey.100', borderRadius: 1,
                  borderBottom: 1, borderColor: 'grey.400', mx: 1,
                }}
              >
                {signatureSet.scores.map((item, index) => (
                  <Box
                    key={item.sample_id}
                    title={`${item.sample_id}: ${formatNumber(item.score)}`}
                    sx={{
                      position: 'absolute',
                      left: `${range === 0 ? 50 : ((item.score - signatureSet.score_minimum) / range) * 100}%`,
                      top: `${8 + (index % 4) * 10}px`,
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      bgcolor: 'primary.main',
                      transform: 'translateX(-50%)',
                    }}
                  />
                ))}
              </Box>
              <TableContainer sx={{ maxHeight: 420 }}>
                <Table size="small" stickyHeader aria-label={`${signatureSet.name} per-sample scores`}>
                  <TableHead>
                    <TableRow>
                      <TableCell>Sample</TableCell>
                      <TableCell align="right">Score</TableCell>
                      <TableCell>Metadata</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {signatureSet.scores.slice(0, 100).map((item) => (
                      <TableRow key={item.sample_id}>
                        <TableCell component="th" scope="row">{item.sample_id}</TableCell>
                        <TableCell align="right">{formatNumber(item.score)}</TableCell>
                        <TableCell>
                          {Object.entries(item.metadata)
                            .filter(([key]) => key !== 'sample_id')
                            .map(([key, value]) => `${key}=${value}`)
                            .join(' · ') || '—'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              {signatureSet.scores.length > 100 && (
                <Typography variant="caption" color="text.secondary">
                  Showing the first 100 samples; download the complete score table below.
                </Typography>
              )}
            </Stack>
          </Paper>
        )
      })}
    </Stack>
  )
}

function SignatureAssociationResults({ summary }: { summary: SignatureScores }) {
  const association = summary.phenotype_association
  if (!association) return null
  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Stack spacing={2.5}>
        <div>
          <Typography variant="overline" color="secondary.main" fontWeight={750}>
            Phenotype association
          </Typography>
          <Typography variant="h5" fontWeight={700}>
            Scores by {association.phenotype_column}
          </Typography>
          <Typography color="text.secondary" mt={0.5}>
            {association.formula} · {association.phenotype_kind} phenotype
            {association.block_column ? ` · blocked by ${association.block_column}` : ''}
          </Typography>
        </div>
        {association.associations.map((result) => {
          const signatureSet = summary.sets.find(
            (item) => item.signature_id === result.signature_id,
          )
          return (
            <Paper key={result.signature_id} variant="outlined" sx={{ p: 2.5 }}>
              <Stack spacing={1.5}>
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  justifyContent="space-between"
                  gap={1}
                >
                  <div>
                    <Typography fontWeight={700}>{result.signature_name}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {result.test.replaceAll('_', ' ')} · n={result.sample_count} · df={result.degrees_of_freedom}
                    </Typography>
                  </div>
                  <Stack direction="row" spacing={1} flexWrap="wrap">
                    <Chip
                      size="small"
                      color={result.adjusted_p_value <= 0.05 ? 'success' : 'default'}
                      label={`FDR ${formatNumber(result.adjusted_p_value)}`}
                    />
                    <Chip size="small" label={`p ${formatNumber(result.p_value)}`} />
                    {result.effect !== null && (
                      <Chip size="small" label={`effect ${formatNumber(result.effect)}`} />
                    )}
                    {result.correlation !== null && (
                      <Chip size="small" label={`r ${formatNumber(result.correlation)}`} />
                    )}
                  </Stack>
                </Stack>
                {signatureSet && (
                  <SignaturePhenotypePlot
                    phenotype={association.phenotype_column}
                    kind={association.phenotype_kind}
                    scores={signatureSet.scores}
                  />
                )}
                {result.group_summaries.length > 0 && (
                  <Stack direction="row" spacing={1} flexWrap="wrap">
                    {result.group_summaries.map((group) => (
                      <Chip
                        key={group.level}
                        variant="outlined"
                        label={`${group.level}: mean ${formatNumber(group.score_mean)} (n=${group.sample_count})`}
                      />
                    ))}
                  </Stack>
                )}
              </Stack>
            </Paper>
          )
        })}
      </Stack>
    </Paper>
  )
}

function SignaturePhenotypePlot({
  phenotype,
  kind,
  scores,
}: {
  phenotype: string
  kind: 'categorical' | 'numeric'
  scores: SignatureScores['sets'][number]['scores']
}) {
  const width = 720
  const height = 270
  const padding = 48
  const values = scores.map((item) => item.score)
  const minimum = Math.min(...values)
  const maximum = Math.max(...values)
  const y = (value: number) => height - padding - (
    (value - minimum) / (maximum - minimum || 1)
  ) * (height - padding * 2)
  if (kind === 'categorical') {
    const levels = [...new Set(scores.map((item) => item.metadata[phenotype]))].sort()
    return (
      <Box sx={{ overflowX: 'auto' }}>
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Scores by ${phenotype}`}>
          <line x1={padding} y1={height - padding} x2={width - 20} y2={height - padding} stroke="#94a3b8" />
          <line x1={padding} y1={20} x2={padding} y2={height - padding} stroke="#94a3b8" />
          {levels.map((level, levelIndex) => {
            const points = scores.filter((item) => item.metadata[phenotype] === level)
            const center = padding + ((levelIndex + 0.5) / levels.length) * (width - padding - 20)
            const mean = points.reduce((sum, item) => sum + item.score, 0) / points.length
            return (
              <g key={level}>
                <line x1={center - 26} x2={center + 26} y1={y(mean)} y2={y(mean)} stroke="#0f172a" strokeWidth="3" />
                {points.map((item, index) => (
                  <circle
                    key={item.sample_id}
                    cx={center + ((index * 37) % 31 - 15)}
                    cy={y(item.score)}
                    r="5"
                    fill={colors[levelIndex % colors.length]}
                    opacity="0.82"
                  >
                    <title>{`${item.sample_id}: ${formatNumber(item.score)}`}</title>
                  </circle>
                ))}
                <text x={center} y={height - 17} textAnchor="middle" fontSize="12">{level}</text>
              </g>
            )
          })}
        </svg>
      </Box>
    )
  }
  const numeric = scores.map((item) => Number(item.metadata[phenotype]))
  const xMinimum = Math.min(...numeric)
  const xMaximum = Math.max(...numeric)
  const x = (value: number) => padding + (
    (value - xMinimum) / (xMaximum - xMinimum || 1)
  ) * (width - padding - 20)
  return (
    <Box sx={{ overflowX: 'auto' }}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Scores by ${phenotype}`}>
        <line x1={padding} y1={height - padding} x2={width - 20} y2={height - padding} stroke="#94a3b8" />
        <line x1={padding} y1={20} x2={padding} y2={height - padding} stroke="#94a3b8" />
        {scores.map((item) => (
          <circle
            key={item.sample_id}
            cx={x(Number(item.metadata[phenotype]))}
            cy={y(item.score)}
            r="5"
            fill="#155e75"
            opacity="0.82"
          >
            <title>{`${item.sample_id}: ${phenotype}=${item.metadata[phenotype]}, score=${formatNumber(item.score)}`}</title>
          </circle>
        ))}
        <text x={width / 2} y={height - 12} textAnchor="middle" fontSize="12">{phenotype}</text>
      </svg>
    </Box>
  )
}

function DifferentialExpressionScatter({
  plot,
  title,
  onSelectFeature,
}: {
  plot: DifferentialExpressionPlot
  title: string
  onSelectFeature?: (featureId: string) => void
}) {
  const points = plot.points.filter(
    (point): point is typeof point & { x: number; y: number } => point.x !== null && point.y !== null,
  )
  const width = 760
  const height = 470
  const padding = 62
  const xs = points.map((point) => point.x)
  const ys = points.map((point) => point.y)
  const scale = (value: number, values: number[], start: number, end: number) => {
    const minimum = Math.min(...values)
    const maximum = Math.max(...values)
    return minimum === maximum ? (start + end) / 2 : start + ((value - minimum) / (maximum - minimum)) * (end - start)
  }
  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Typography variant="h5" fontWeight={700}>{title}</Typography>
      <Typography color="text.secondary">
        Hover for statistics or select a point to open its gene-level detail panel.
      </Typography>
      <Box sx={{ overflowX: 'auto', mt: 2 }}>
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title} style={{ minWidth: 620, width: '100%' }}>
          <line x1={padding} y1={height - padding} x2={width - 25} y2={height - padding} stroke="#9ca3af" />
          <line x1={padding} y1={25} x2={padding} y2={height - padding} stroke="#9ca3af" />
          {points.map((point) => (
            <circle
              key={point.feature_id}
              cx={scale(point.x, xs, padding + 8, width - 32)}
              cy={scale(point.y, ys, height - padding - 8, 32)}
              r={point.significant ? 4 : 2.5}
              fill={point.significant ? '#be123c' : '#64748b'}
              opacity={point.significant ? 0.9 : 0.55}
              role="button"
              aria-label={`Open ${point.feature_id} details`}
              tabIndex={0}
              onClick={() => onSelectFeature?.(point.feature_id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onSelectFeature?.(point.feature_id)
                }
              }}
              style={{ cursor: onSelectFeature ? 'pointer' : 'default' }}
            >
              <title>{`${point.feature_id}\n${plot.x_label}: ${point.x.toFixed(3)}\n${plot.y_label}: ${point.y.toFixed(3)}\nadjusted p: ${point.adjusted_p_value?.toExponential(3) ?? 'NA'}`}</title>
            </circle>
          ))}
          <text x={width / 2} y={height - 12} textAnchor="middle" fontSize="14">{plot.x_label}</text>
          <text x="16" y={height / 2} textAnchor="middle" fontSize="14" transform={`rotate(-90 16 ${height / 2})`}>{plot.y_label}</text>
        </svg>
      </Box>
    </Paper>
  )
}

const resultColumns: Array<{
  key: DifferentialExpressionSort
  label: string
  align?: 'left' | 'right' | 'center'
}> = [
  { key: 'feature_id', label: 'Feature' },
  { key: 'gene_symbol', label: 'Symbol' },
  { key: 'base_expression', label: 'Abundance', align: 'right' },
  { key: 'log2_fold_change', label: 'log2 FC', align: 'right' },
  { key: 'standard_error', label: 'SE', align: 'right' },
  { key: 'statistic', label: 'Statistic', align: 'right' },
  { key: 'p_value', label: 'P-value', align: 'right' },
  { key: 'adjusted_p_value', label: 'Adjusted p', align: 'right' },
  { key: 'significant', label: 'Call', align: 'center' },
]

function DifferentialExpressionResultsExplorer({
  runId,
  onSelectFeature,
}: {
  runId: string
  onSelectFeature: (featureId: string) => void
}) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [fdrMax, setFdrMax] = useState('')
  const [absoluteFoldChange, setAbsoluteFoldChange] = useState('')
  const [significantOnly, setSignificantOnly] = useState(false)
  const [sortBy, setSortBy] = useState<DifferentialExpressionSort>('adjusted_p_value')
  const [direction, setDirection] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(0)
  const [selectedFeatures, setSelectedFeatures] = useState<Set<string>>(() => new Set())
  const [signatureDialogOpen, setSignatureDialogOpen] = useState(false)
  const [signatureName, setSignatureName] = useState('Candidate gene signature')
  const [signatureDescription, setSignatureDescription] = useState('')
  const [savedSignatureName, setSavedSignatureName] = useState<string | null>(null)
  const limit = 25
  const query = useMemo<DifferentialExpressionResultQuery>(() => ({
    search,
    fdrMax: fdrMax === '' ? undefined : Number(fdrMax),
    absoluteLog2FoldChangeMin: absoluteFoldChange === '' ? undefined : Number(absoluteFoldChange),
    significantOnly,
    sortBy,
    direction,
    offset: page * limit,
    limit,
  }), [absoluteFoldChange, direction, fdrMax, page, search, significantOnly, sortBy])
  const results = useQuery({
    queryKey: ['differential-expression-results', runId, query],
    queryFn: ({ signal }) => fetchDifferentialExpressionResults(runId, query, signal),
  })
  const signatures = useQuery({
    queryKey: ['run-signatures', runId],
    queryFn: ({ signal }) => fetchRunSignatures(runId, signal),
  })
  const saveSignature = useMutation({
    mutationFn: () => createGeneSignature(runId, {
      name: signatureName,
      description: signatureDescription.trim() || undefined,
      feature_ids: Array.from(selectedFeatures),
      selection: {
        mode: 'manual',
        search: search.trim() || undefined,
        fdr_max: fdrMax === '' ? undefined : Number(fdrMax),
        absolute_log2_fold_change_min:
          absoluteFoldChange === '' ? undefined : Number(absoluteFoldChange),
        significant_only: significantOnly,
        sort_by: sortBy,
        direction,
      },
    }),
    onSuccess: (signature) => {
      setSignatureDialogOpen(false)
      setSelectedFeatures(new Set())
      setSavedSignatureName(signature.name)
      setSignatureDescription('')
      queryClient.invalidateQueries({ queryKey: ['run-signatures', runId] })
    },
  })
  const updateSort = (column: DifferentialExpressionSort) => {
    setPage(0)
    if (sortBy === column) setDirection((value) => value === 'asc' ? 'desc' : 'asc')
    else {
      setSortBy(column)
      setDirection(column === 'feature_id' || column === 'gene_symbol' ? 'asc' : 'desc')
    }
  }
  const updateFilter = (update: () => void) => {
    setPage(0)
    update()
  }
  const pageStart = results.data?.total ? page * limit + 1 : 0
  const pageEnd = Math.min((page + 1) * limit, results.data?.total ?? 0)
  const pageFeatureIds = results.data?.items.map((row) => row.feature_id) ?? []
  const selectedOnPage = pageFeatureIds.filter((featureId) => selectedFeatures.has(featureId)).length
  const setFeatureSelected = (featureId: string, selected: boolean) => {
    setSavedSignatureName(null)
    setSelectedFeatures((current) => {
      const next = new Set(current)
      if (selected && next.size < 500) next.add(featureId)
      else next.delete(featureId)
      return next
    })
  }
  const setPageSelected = (selected: boolean) => {
    setSavedSignatureName(null)
    setSelectedFeatures((current) => {
      const next = new Set(current)
      for (const featureId of pageFeatureIds) {
        if (selected && next.size < 500) next.add(featureId)
        else next.delete(featureId)
      }
      return next
    })
  }

  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Stack direction={{ xs: 'column', lg: 'row' }} justifyContent="space-between" gap={2}>
        <Box>
          <Typography variant="h5" fontWeight={700}>Differential-expression results</Typography>
          <Typography color="text.secondary">
            Search, filter, and sort the complete result table. Select any row for gene-level details.
          </Typography>
        </Box>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ alignSelf: 'flex-start' }}>
          <Button
            variant="contained"
            disabled={selectedFeatures.size === 0}
            onClick={() => setSignatureDialogOpen(true)}
          >
            {selectedFeatures.size > 0
              ? `Save ${selectedFeatures.size} selected as signature`
              : 'Save selected genes as signature'}
          </Button>
          <Button
            component="a"
            href={filteredDifferentialExpressionDownloadUrl(runId, query)}
            startIcon={<DownloadRoundedIcon />}
            variant="outlined"
          >
            Download filtered table
          </Button>
        </Stack>
      </Stack>
      {savedSignatureName && (
        <Alert severity="success" sx={{ mt: 2 }}>
          Saved “{savedSignatureName}” as a provenance-frozen signature draft.
        </Alert>
      )}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} mt={3} alignItems="center">
        <TextField
          label="Search gene symbol or ID"
          value={search}
          onChange={(event) => updateFilter(() => setSearch(event.target.value))}
          size="small"
          sx={{ minWidth: 260 }}
        />
        <TextField
          label="Maximum adjusted p-value"
          value={fdrMax}
          onChange={(event) => updateFilter(() => setFdrMax(event.target.value))}
          type="number"
          size="small"
          slotProps={{ htmlInput: { min: 0, max: 1, step: 0.01 } }}
        />
        <TextField
          label="Minimum absolute log2 FC"
          value={absoluteFoldChange}
          onChange={(event) => updateFilter(() => setAbsoluteFoldChange(event.target.value))}
          type="number"
          size="small"
          slotProps={{ htmlInput: { min: 0, step: 0.1 } }}
        />
        <FormControlLabel
          control={(
            <Checkbox
              checked={significantOnly}
              onChange={(event) => updateFilter(() => setSignificantOnly(event.target.checked))}
            />
          )}
          label="Significant only"
        />
      </Stack>
      {results.isPending && <LoadingState label="Loading result table…" />}
      {results.isError && <ErrorState error={results.error} />}
      {results.data && (
        <>
          <Typography variant="caption" color="text.secondary" display="block" mt={2}>
            {results.data.total.toLocaleString()} matching features · abundance is {results.data.base_expression_label.toLowerCase()}
          </Typography>
          <TableContainer sx={{ mt: 1 }}>
            <Table size="small" aria-label="Differential-expression results">
              <TableHead>
                <TableRow>
                  <TableCell padding="checkbox">
                    <Checkbox
                      inputProps={{ 'aria-label': 'Select all features on this page' }}
                      checked={pageFeatureIds.length > 0 && selectedOnPage === pageFeatureIds.length}
                      indeterminate={selectedOnPage > 0 && selectedOnPage < pageFeatureIds.length}
                      onChange={(event) => setPageSelected(event.target.checked)}
                    />
                  </TableCell>
                  {resultColumns.map((column) => (
                    <TableCell key={column.key} align={column.align ?? 'left'}>
                      <TableSortLabel
                        active={sortBy === column.key}
                        direction={sortBy === column.key ? direction : 'asc'}
                        onClick={() => updateSort(column.key)}
                      >
                        {column.label}
                      </TableSortLabel>
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {results.data.items.map((row) => (
                  <TableRow
                    hover
                    key={row.feature_id}
                    tabIndex={0}
                    onClick={() => onSelectFeature(row.feature_id)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        onSelectFeature(row.feature_id)
                      }
                    }}
                    sx={{ cursor: 'pointer' }}
                  >
                    <TableCell
                      padding="checkbox"
                      onClick={(event) => event.stopPropagation()}
                      onKeyDown={(event) => event.stopPropagation()}
                    >
                      <Checkbox
                        inputProps={{ 'aria-label': `Select ${row.feature_id} for signature` }}
                        checked={selectedFeatures.has(row.feature_id)}
                        disabled={selectedFeatures.size >= 500 && !selectedFeatures.has(row.feature_id)}
                        onChange={(event) => setFeatureSelected(row.feature_id, event.target.checked)}
                      />
                    </TableCell>
                    <TableCell component="th" scope="row" sx={{ fontFamily: 'monospace' }}>
                      {row.feature_id}
                    </TableCell>
                    <TableCell>{row.gene_symbol ?? '—'}</TableCell>
                    <TableCell align="right">{formatNumber(row.base_expression)}</TableCell>
                    <TableCell align="right">{formatNumber(row.log2_fold_change)}</TableCell>
                    <TableCell align="right">{formatNumber(row.standard_error)}</TableCell>
                    <TableCell align="right">{formatNumber(row.statistic)}</TableCell>
                    <TableCell align="right">{formatPValue(row.p_value)}</TableCell>
                    <TableCell align="right">{formatPValue(row.adjusted_p_value)}</TableCell>
                    <TableCell align="center">
                      <Chip
                        size="small"
                        color={row.significant ? 'success' : 'default'}
                        label={row.significant ? 'Significant' : 'Not called'}
                      />
                    </TableCell>
                  </TableRow>
                ))}
                {results.data.items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={resultColumns.length + 1} align="center">
                      No features match the current filters.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
          <Stack direction="row" justifyContent="space-between" alignItems="center" mt={2}>
            <Typography variant="body2" color="text.secondary">
              Showing {pageStart.toLocaleString()}–{pageEnd.toLocaleString()} of {results.data.total.toLocaleString()}
            </Typography>
            <Stack direction="row" spacing={1}>
              <Button size="small" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>
                Previous
              </Button>
              <Button
                size="small"
                disabled={pageEnd >= results.data.total}
                onClick={() => setPage((value) => value + 1)}
              >
                Next
              </Button>
            </Stack>
          </Stack>
          {signatures.data && signatures.data.length > 0 && (
            <>
              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle1" fontWeight={700}>Saved signature drafts</Typography>
              <Stack spacing={1} mt={1}>
                {signatures.data.map((signature) => (
                  <Paper variant="outlined" sx={{ p: 1.5 }} key={signature.id}>
                    <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={1}>
                      <Box>
                        <Typography fontWeight={700}>{signature.name}</Typography>
                        <Typography variant="body2" color="text.secondary">
                          {signature.feature_ids.length} candidate genes · source checksum {String(signature.selection_json.source_result_sha256).slice(0, 12)}…
                        </Typography>
                      </Box>
                      <Chip label="Draft · unvalidated" color="warning" size="small" />
                    </Stack>
                  </Paper>
                ))}
              </Stack>
            </>
          )}
        </>
      )}
      <Dialog
        open={signatureDialogOpen}
        onClose={() => !saveSignature.isPending && setSignatureDialogOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Save candidate gene signature</DialogTitle>
        <DialogContent>
          <Stack spacing={2} mt={1}>
            <Alert severity="warning">
              Selecting genes from this result is candidate generation, not independent validation.
              The draft must not be treated as a diagnostic or clinically validated signature.
            </Alert>
            <Typography>
              {selectedFeatures.size} selected feature{selectedFeatures.size === 1 ? '' : 's'} will
              be frozen with this run’s result checksum and current filter context.
            </Typography>
            <TextField
              autoFocus
              label="Signature name"
              value={signatureName}
              onChange={(event) => setSignatureName(event.target.value)}
              required
              inputProps={{ maxLength: 200 }}
            />
            <TextField
              label="Description"
              value={signatureDescription}
              onChange={(event) => setSignatureDescription(event.target.value)}
              multiline
              minRows={3}
              inputProps={{ maxLength: 5000 }}
            />
            {saveSignature.isError && <ErrorState error={saveSignature.error} />}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSignatureDialogOpen(false)} disabled={saveSignature.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={() => saveSignature.mutate()}
            disabled={saveSignature.isPending || !signatureName.trim() || selectedFeatures.size === 0}
          >
            Save signature draft
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  )
}

function EnrichmentPanel({ summary }: { summary: EnrichmentSummary }) {
  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Typography variant="h5" fontWeight={700}>Gene-set enrichment</Typography>
      <Typography color="text.secondary" mt={0.5}>
        Ranked-list enrichment and over-representation analysis against a frozen collection.
      </Typography>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} mt={2} flexWrap="wrap">
        <Chip label={`${summary.collection.name} · v${summary.collection.version}`} />
        <Chip label={`${summary.collection.set_count} sets`} variant="outlined" />
        <Chip label={`${summary.parameters.permutation_count} permutations`} variant="outlined" />
        <Chip label={`Seed ${summary.parameters.random_seed}`} variant="outlined" />
      </Stack>
      <Typography variant="body2" color="text.secondary" mt={1.5} sx={{ overflowWrap: 'anywhere' }}>
        Collection SHA-256: <code>{summary.collection.gmt_sha256}</code><br />
        Source result SHA-256: <code>{summary.source_result.result_sha256}</code><br />
        Namespace: {summary.collection.identifier_namespace} · Source: {summary.collection.source}
        {' '}· License: {summary.collection.license}
      </Typography>
      {summary.warnings.map((warning) => (
        <Alert severity="warning" sx={{ mt: 2 }} key={warning}>{warning}</Alert>
      ))}
      <Stack direction={{ xs: 'column', xl: 'row' }} spacing={3} mt={3} alignItems="flex-start">
        <EnrichmentResultsTable
          title="Ranked-list enrichment"
          results={summary.ranked_list}
          effectLabel="NES"
          effect={(item) => item.normalized_enrichment_score}
        />
        <EnrichmentResultsTable
          title="Over-representation analysis"
          results={summary.over_representation}
          effectLabel="Odds ratio"
          effect={(item) => item.odds_ratio}
        />
      </Stack>
      <Alert severity="info" sx={{ mt: 3 }}>
        Enrichment is exploratory and collection-dependent. It does not independently validate
        individual genes, pathways, or clinical utility.
      </Alert>
    </Paper>
  )
}

function EnrichmentResultsTable({
  title,
  results,
  effectLabel,
  effect,
}: {
  title: string
  results: EnrichmentResult[]
  effectLabel: string
  effect: (item: EnrichmentResult) => number | null
}) {
  return (
    <Box sx={{ flex: 1, minWidth: 0, width: '100%' }}>
      <Typography variant="h6" fontWeight={700}>{title}</Typography>
      <TableContainer sx={{ mt: 1 }}>
        <Table size="small" aria-label={title}>
          <TableHead>
            <TableRow>
              <TableCell>Gene set</TableCell>
              <TableCell>Direction</TableCell>
              <TableCell align="right">Overlap</TableCell>
              <TableCell align="right">{effectLabel}</TableCell>
              <TableCell align="right">Adjusted p</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {results.slice(0, 8).map((item) => (
              <TableRow key={item.gene_set_id}>
                <TableCell>
                  <Typography variant="body2" fontWeight={650}>{item.gene_set_id}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {item.gene_set_name}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip
                    label={item.direction}
                    size="small"
                    color={item.direction === 'up' ? 'success' : item.direction === 'down' ? 'error' : 'default'}
                    variant="outlined"
                  />
                </TableCell>
                <TableCell align="right">{item.overlap_size}/{item.set_size}</TableCell>
                <TableCell align="right">{formatNumber(effect(item))}</TableCell>
                <TableCell align="right">{formatPValue(item.adjusted_p_value)}</TableCell>
              </TableRow>
            ))}
            {results.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} align="center">No eligible gene sets.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  )
}

function GeneDetailDrawer({
  runId,
  featureId,
  onClose,
}: {
  runId: string
  featureId: string | null
  onClose: () => void
}) {
  const detail = useQuery({
    queryKey: ['differential-expression-feature', runId, featureId],
    queryFn: ({ signal }) => fetchDifferentialExpressionFeature(runId, featureId!, signal),
    enabled: Boolean(featureId),
  })
  return (
    <Drawer anchor="right" open={Boolean(featureId)} onClose={onClose}>
      <Box sx={{ width: { xs: '100vw', sm: 560 }, maxWidth: '100vw', p: 3 }} role="dialog" aria-label="Gene detail">
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
          <Box>
            <Typography variant="overline" color="secondary.main">Gene-level detail</Typography>
            <Typography variant="h4" fontWeight={750}>{featureId}</Typography>
          </Box>
          <IconButton onClick={onClose} aria-label="Close gene detail">
            <CloseRoundedIcon />
          </IconButton>
        </Stack>
        {detail.isPending && featureId && <LoadingState label="Loading gene detail…" />}
        {detail.isError && <ErrorState error={detail.error} />}
        {detail.data && <GeneDetailContent detail={detail.data} />}
      </Box>
    </Drawer>
  )
}

function GeneDetailContent({ detail }: { detail: DifferentialExpressionFeatureDetail }) {
  const result = detail.result
  const statistics = [
    [detail.base_expression_label, formatNumber(result.base_expression)],
    ['log2 fold change', formatNumber(result.log2_fold_change)],
    ['Standard error', formatNumber(result.standard_error)],
    ['Statistic', formatNumber(result.statistic)],
    ['P-value', formatPValue(result.p_value)],
    ['Adjusted p-value', formatPValue(result.adjusted_p_value)],
  ]
  return (
    <Stack spacing={3} mt={3}>
      <Stack direction="row" spacing={1} flexWrap="wrap">
        {result.gene_symbol && <Chip label={result.gene_symbol} />}
        {result.method && <Chip label={result.method} variant="outlined" />}
        <Chip
          label={result.significant ? 'Significant' : 'Not called significant'}
          color={result.significant ? 'success' : 'default'}
        />
      </Stack>
      {result.contrast && <Typography><strong>Contrast:</strong> {result.contrast}</Typography>}
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 1.5 }}>
        {statistics.map(([label, value]) => (
          <Paper variant="outlined" sx={{ p: 1.5 }} key={label}>
            <Typography variant="caption" color="text.secondary" display="block">{label}</Typography>
            <Typography fontWeight={700}>{value}</Typography>
          </Paper>
        ))}
      </Box>
      {detail.expression_profile ? (
        <FeatureExpressionChart detail={detail} />
      ) : (
        <Alert severity="info">
          Expression profiles were not published by this older run. Run the saved analysis again to add them.
        </Alert>
      )}
      <Alert severity="info">
        This single-feature view is exploratory and for research use only; interpret it with the full model and multiple-testing correction.
      </Alert>
    </Stack>
  )
}

function FeatureExpressionChart({ detail }: { detail: DifferentialExpressionFeatureDetail }) {
  const profile = detail.expression_profile!
  const variable = profile.contrast.variable
  const levels = profile.group_summaries.map((group) => group.level)
  const width = 500
  const height = 330
  const padding = 55
  const values = profile.values.map((item) => item.value)
  const minimum = Math.min(...values)
  const maximum = Math.max(...values)
  const y = (value: number) => maximum === minimum
    ? height / 2
    : height - padding - ((value - minimum) / (maximum - minimum)) * (height - padding * 1.5)
  const x = (level: string) => {
    const index = Math.max(0, levels.indexOf(level))
    return padding + ((index + 0.5) / Math.max(levels.length, 1)) * (width - padding * 1.5)
  }
  return (
    <Box>
      <Typography variant="h6" fontWeight={700}>Expression by {variable}</Typography>
      <Typography color="text.secondary">{profile.source} · {profile.assay}</Typography>
      <Box sx={{ overflowX: 'auto', mt: 1 }}>
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Per-gene expression plot" style={{ minWidth: 440, width: '100%' }}>
          <line x1={padding} y1={height - padding} x2={width - 20} y2={height - padding} stroke="#9ca3af" />
          <line x1={padding} y1={25} x2={padding} y2={height - padding} stroke="#9ca3af" />
          {profile.values.map((item, index) => {
            const level = item.metadata[variable] ?? 'Unavailable'
            const jitter = ((index % 9) - 4) * 3.5
            return (
              <circle
                key={item.sample_id}
                cx={x(level) + jitter}
                cy={y(item.value)}
                r="4"
                fill={colors[Math.max(0, levels.indexOf(level)) % colors.length]}
                opacity="0.72"
              >
                <title>{`${item.sample_id}\n${variable}: ${level}\nexpression: ${item.value.toFixed(3)}`}</title>
              </circle>
            )
          })}
          {profile.group_summaries.map((group) => (
            <g key={group.level}>
              <line
                x1={x(group.level) - 28}
                x2={x(group.level) + 28}
                y1={y(group.mean)}
                y2={y(group.mean)}
                stroke="#111827"
                strokeWidth="3"
              />
              <text x={x(group.level)} y={height - padding + 20} textAnchor="middle" fontSize="12">
                {group.level} (n={group.sample_count})
              </text>
            </g>
          ))}
          <text x="16" y={height / 2} textAnchor="middle" fontSize="13" transform={`rotate(-90 16 ${height / 2})`}>
            {profile.value_label}
          </text>
        </svg>
      </Box>
      <Typography variant="caption" color="text.secondary">
        Points are samples; horizontal bars are group means.
      </Typography>
    </Box>
  )
}

function formatNumber(value: number | null): string {
  return value === null ? 'NA' : value.toLocaleString(undefined, { maximumSignificantDigits: 4 })
}

function formatPValue(value: number | null): string {
  if (value === null) return 'NA'
  return value < 0.001 ? value.toExponential(2) : value.toPrecision(3)
}

function PValueDistributionChart({ distribution }: { distribution: PValueDistribution }) {
  const width = 760
  const height = 360
  const left = 62
  const bottom = 62
  const top = 24
  const plotWidth = width - left - 24
  const plotHeight = height - bottom - top
  const maximum = Math.max(...distribution.bins.map((bin) => bin.count), 1)
  const barWidth = plotWidth / Math.max(distribution.bins.length, 1)
  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Typography variant="h5" fontWeight={700}>P-value distribution</Typography>
      <Typography color="text.secondary">
        {distribution.finite_p_value_count.toLocaleString()} finite tests across fixed-width bins
        {distribution.missing_p_value_count > 0
          ? ` · ${distribution.missing_p_value_count.toLocaleString()} unavailable p-values`
          : ''}.
      </Typography>
      <Box sx={{ overflowX: 'auto', mt: 2 }}>
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="P-value distribution" style={{ minWidth: 620, width: '100%' }}>
          <line x1={left} y1={height - bottom} x2={width - 24} y2={height - bottom} stroke="#9ca3af" />
          <line x1={left} y1={top} x2={left} y2={height - bottom} stroke="#9ca3af" />
          {distribution.bins.map((bin, index) => {
            const barHeight = (bin.count / maximum) * plotHeight
            return (
              <g key={bin.start}>
                <rect
                  x={left + index * barWidth + 1}
                  y={height - bottom - barHeight}
                  width={Math.max(barWidth - 2, 1)}
                  height={barHeight}
                  fill="#155e75"
                >
                  <title>{`${bin.start.toFixed(2)}–${bin.end.toFixed(2)}: ${bin.count.toLocaleString()} features`}</title>
                </rect>
                {index % 4 === 0 && (
                  <text x={left + index * barWidth} y={height - bottom + 18} fontSize="10" textAnchor="middle">
                    {bin.start.toFixed(2)}
                  </text>
                )}
              </g>
            )
          })}
          <text x={left - 8} y={top + 4} fontSize="10" textAnchor="end">{maximum}</text>
          <text x={width / 2} y={height - 12} textAnchor="middle" fontSize="14">P-value</text>
          <text x="16" y={height / 2} textAnchor="middle" fontSize="14" transform={`rotate(-90 16 ${height / 2})`}>Feature count</text>
        </svg>
      </Box>
    </Paper>
  )
}

function DifferentialExpressionHeatmap({ heatmap }: { heatmap: ExpressionHeatmap }) {
  const left = 190
  const top = 24
  const bottom = 120
  const cellWidth = 14
  const cellHeight = 18
  const gridWidth = heatmap.sample_ids.length * cellWidth
  const gridHeight = heatmap.feature_ids.length * cellHeight
  const width = Math.max(800, left + gridWidth + 35)
  const height = top + gridHeight + bottom
  const contrastLevels = [heatmap.contrast.denominator, heatmap.contrast.numerator]
  const contrastColors = new Map(contrastLevels.map((level, index) => [level, colors[index]]))
  const labelStep = Math.max(1, Math.ceil(heatmap.sample_ids.length / 36))
  const zColor = (value: number) => {
    const bounded = Math.max(-3, Math.min(3, value)) / 3
    const target = bounded < 0 ? [37, 99, 235] : [190, 18, 60]
    const strength = Math.abs(bounded)
    return `rgb(${target.map((channel) => Math.round(248 + (channel - 248) * strength)).join(',')})`
  }
  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Typography variant="h5" fontWeight={700}>Top-feature expression heatmap</Typography>
      <Typography color="text.secondary">
        {heatmap.feature_ids.length} features · {heatmap.source} · row z-scores · ordered by {heatmap.sample_ordering}.
      </Typography>
      <Box sx={{ overflowX: 'auto', mt: 2 }}>
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Top-feature expression heatmap" style={{ minWidth: width, width: '100%' }}>
          {heatmap.values.flatMap((row, featureIndex) => row.map((value, sampleIndex) => {
            const featureId = heatmap.feature_ids[featureIndex]
            const sampleId = heatmap.sample_ids[sampleIndex]
            const annotation = heatmap.feature_annotations[featureId]
            const sampleMetadata = heatmap.metadata[sampleId] ?? {}
            return (
              <rect
                key={`${featureId}-${sampleId}`}
                x={left + sampleIndex * cellWidth}
                y={top + featureIndex * cellHeight}
                width={cellWidth + 0.2}
                height={cellHeight + 0.2}
                fill={zColor(value)}
              >
                <title>{`${featureId}\n${sampleId}\nz-score: ${value.toFixed(3)}\nlog2 FC: ${annotation?.log2_fold_change?.toFixed(3) ?? 'NA'}\nadjusted p: ${annotation?.adjusted_p_value?.toExponential(3) ?? 'NA'}\n${heatmap.contrast.variable}: ${sampleMetadata[heatmap.contrast.variable] ?? 'NA'}`}</title>
              </rect>
            )
          }))}
          {heatmap.feature_ids.map((featureId, index) => (
            <text key={featureId} x={left - 7} y={top + index * cellHeight + 13} textAnchor="end" fontSize="10">
              {featureId}
            </text>
          ))}
          {heatmap.sample_ids.map((sampleId, index) => {
            const level = heatmap.metadata[sampleId]?.[heatmap.contrast.variable]
            return (
              <g key={sampleId}>
                <rect
                  x={left + index * cellWidth}
                  y={top + gridHeight + 3}
                  width={cellWidth + 0.2}
                  height="8"
                  fill={contrastColors.get(level) ?? '#94a3b8'}
                >
                  <title>{`${sampleId}\n${heatmap.contrast.variable}: ${level ?? 'NA'}`}</title>
                </rect>
                {index % labelStep === 0 && (
                  <text
                    x={left + index * cellWidth + 6}
                    y={top + gridHeight + 18}
                    fontSize="8"
                    textAnchor="end"
                    transform={`rotate(-62 ${left + index * cellWidth + 6} ${top + gridHeight + 18})`}
                  >
                    {sampleId}
                  </text>
                )}
              </g>
            )
          })}
        </svg>
      </Box>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="center" alignItems="center">
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="caption">−3</Typography>
          <Box sx={{ width: 150, height: 10, background: 'linear-gradient(90deg, #2563eb, #f8fafc 50%, #be123c)' }} />
          <Typography variant="caption">+3 z-score</Typography>
        </Stack>
        {contrastLevels.map((level) => (
          <Stack direction="row" spacing={0.5} alignItems="center" key={level}>
            <Box sx={{ width: 10, height: 10, bgcolor: contrastColors.get(level) }} />
            <Typography variant="caption">{level}</Typography>
          </Stack>
        ))}
      </Stack>
    </Paper>
  )
}

interface ScatterPoint {
  sample_id: string
  coordinates: Record<string, number>
  metadata: Record<string, string>
}

function CoordinateScatter({
  axes,
  points,
  methodLabel,
}: {
  axes: Array<{ name: string; explainedVarianceRatio?: number }>
  points: ScatterPoint[]
  methodLabel: string
}) {
  const components = axes.map((axis) => axis.name)
  const metadataColumns = useMemo(
    () => Object.keys(points[0]?.metadata ?? {}).filter((column) => column !== 'sample_id'),
    [points],
  )
  const [xAxis, setXAxis] = useState(components[0] ?? 'PC1')
  const [yAxis, setYAxis] = useState(components[1] ?? components[0] ?? 'PC2')
  const [colorBy, setColorBy] = useState(metadataColumns[0] ?? 'sample_id')
  useEffect(() => {
    if (!metadataColumns.includes(colorBy)) setColorBy(metadataColumns[0] ?? 'sample_id')
  }, [colorBy, metadataColumns])
  const valuesX = points.map((point) => point.coordinates[xAxis] ?? 0)
  const valuesY = points.map((point) => point.coordinates[yAxis] ?? 0)
  const categories = Array.from(new Set(points.map((point) => point.metadata[colorBy] ?? point.sample_id)))
  const colorMap = new Map(categories.map((category, index) => [category, colors[index % colors.length]]))
  const width = 760
  const height = 470
  const padding = 62
  const scale = (value: number, values: number[], start: number, end: number) => {
    const min = Math.min(...values)
    const max = Math.max(...values)
    return min === max ? (start + end) / 2 : start + ((value - min) / (max - min)) * (end - start)
  }
  const ratio = (component: string) => axes.find((axis) => axis.name === component)?.explainedVarianceRatio
  const axisLabel = (component: string) => {
    const explained = ratio(component)
    return explained === undefined ? component : `${component} (${(explained * 100).toFixed(1)}%)`
  }

  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" gap={2}>
        <Box>
          <Typography variant="h5" fontWeight={700}>{methodLabel} sample coordinates</Typography>
          <Typography color="text.secondary">Hover over a point for sample metadata.</Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <AxisSelect label="X axis" value={xAxis} components={components} onChange={setXAxis} />
          <AxisSelect label="Y axis" value={yAxis} components={components} onChange={setYAxis} />
          <FormControl size="small" sx={{ minWidth: 130 }}>
            <InputLabel>Color by</InputLabel>
            <Select label="Color by" value={colorBy} onChange={(event) => setColorBy(event.target.value)}>
              {metadataColumns.map((column) => <MenuItem key={column} value={column}>{column}</MenuItem>)}
            </Select>
          </FormControl>
        </Stack>
      </Stack>
      <Box sx={{ overflowX: 'auto', mt: 2 }}>
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${methodLabel} scatter plot`} style={{ minWidth: 620, width: '100%' }}>
          <line x1={padding} y1={height - padding} x2={width - 25} y2={height - padding} stroke="#9ca3af" />
          <line x1={padding} y1={25} x2={padding} y2={height - padding} stroke="#9ca3af" />
          {points.map((point, index) => {
            const category = point.metadata[colorBy] ?? point.sample_id
            return (
              <circle
                key={point.sample_id}
                cx={scale(valuesX[index], valuesX, padding + 12, width - 38)}
                cy={scale(valuesY[index], valuesY, height - padding - 12, 38)}
                r="8"
                fill={colorMap.get(category)}
                stroke="white"
                strokeWidth="2"
                style={{ cursor: 'crosshair' }}
              >
                <title>{`${point.sample_id}\n${colorBy}: ${category}\n${xAxis}: ${valuesX[index].toFixed(3)}\n${yAxis}: ${valuesY[index].toFixed(3)}`}</title>
              </circle>
            )
          })}
          <text x={width / 2} y={height - 12} textAnchor="middle" fontSize="14">{axisLabel(xAxis)}</text>
          <text x="16" y={height / 2} textAnchor="middle" fontSize="14" transform={`rotate(-90 16 ${height / 2})`}>{axisLabel(yAxis)}</text>
        </svg>
      </Box>
      <Stack direction="row" spacing={2} justifyContent="center" flexWrap="wrap">
        {categories.map((category) => (
          <Stack key={category} direction="row" spacing={0.75} alignItems="center">
            <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: colorMap.get(category) }} />
            <Typography variant="caption">{category}</Typography>
          </Stack>
        ))}
      </Stack>
    </Paper>
  )
}

function EmbeddingResult({ plot }: { plot: EmbeddingPlot }) {
  const label = plot.method === 'umap' ? 'UMAP' : 't-SNE'
  return (
    <CoordinateScatter
      axes={plot.axes.map((axis) => ({ name: axis }))}
      points={plot.points}
      methodLabel={label}
    />
  )
}

function DendrogramChart({ plot }: { plot: DendrogramPlot }) {
  const width = Math.max(900, plot.sample_order.length * 15)
  const height = 500
  const top = 24
  const bottom = 120
  const maximumX = Math.max(...plot.icoord.flat(), 1)
  const maximumY = Math.max(...plot.dcoord.flat(), 1)
  const x = (value: number) => 20 + (value / maximumX) * (width - 40)
  const y = (value: number) => height - bottom - (value / maximumY) * (height - bottom - top)
  const clusters = Array.from(new Set(Object.values(plot.clusters))).sort((a, b) => a - b)

  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Typography variant="h5" fontWeight={700}>Sample dendrogram</Typography>
      <Typography color="text.secondary">
        Branch height represents dissimilarity; downloadable assignments preserve the selected cut.
      </Typography>
      <Box sx={{ overflowX: 'auto', mt: 2 }}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label="Hierarchical sample dendrogram"
          style={{ minWidth: width, width: '100%' }}
        >
          {plot.icoord.map((xCoordinates, index) => (
            <polyline
              key={`${xCoordinates[0]}-${index}`}
              points={xCoordinates
                .map((value, point) => `${x(value)},${y(plot.dcoord[index][point])}`)
                .join(' ')}
              fill="none"
              stroke="#155e75"
              strokeWidth="1.5"
            />
          ))}
          {plot.sample_order.map((sampleId, index) => {
            const position = 5 + index * 10
            return (
              <text
                key={sampleId}
                x={x(position)}
                y={height - bottom + 8}
                fontSize="9"
                textAnchor="end"
                transform={`rotate(-62 ${x(position)} ${height - bottom + 8})`}
              >
                {sampleId}
              </text>
            )
          })}
        </svg>
      </Box>
      <Stack direction="row" spacing={1} flexWrap="wrap">
        {clusters.map((cluster) => (
          <Chip
            key={cluster}
            size="small"
            label={`Cluster ${cluster}: ${Object.values(plot.clusters).filter((value) => value === cluster).length} samples`}
            variant="outlined"
          />
        ))}
      </Stack>
    </Paper>
  )
}

function CorrelationChart({ heatmap }: { heatmap: CorrelationHeatmap }) {
  const size = 760
  const count = heatmap.sample_order.length
  const cell = size / Math.max(count, 1)
  const correlationColor = (value: number) => {
    const bounded = Math.max(-1, Math.min(1, value))
    const target = bounded >= 0 ? [21, 94, 117] : [190, 18, 60]
    const strength = Math.abs(bounded)
    return `rgb(${target.map((channel) => Math.round(255 + (channel - 255) * strength)).join(',')})`
  }
  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Typography variant="h5" fontWeight={700}>Sample correlation heatmap</Typography>
      <Typography color="text.secondary">Samples use the dendrogram leaf order. Hover for pairwise values.</Typography>
      <Box sx={{ maxWidth: 780, mx: 'auto', mt: 2 }}>
        <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Sample correlation heatmap" style={{ width: '100%' }}>
          {heatmap.values.flatMap((row, rowIndex) =>
            row.map((value, columnIndex) => (
              <rect
                key={`${rowIndex}-${columnIndex}`}
                x={columnIndex * cell}
                y={rowIndex * cell}
                width={cell + 0.15}
                height={cell + 0.15}
                fill={correlationColor(value)}
              >
                <title>{`${heatmap.sample_order[rowIndex]} × ${heatmap.sample_order[columnIndex]}: ${value.toFixed(3)}`}</title>
              </rect>
            )),
          )}
        </svg>
      </Box>
      <Stack direction="row" justifyContent="center" spacing={1} alignItems="center">
        <Typography variant="caption">−1</Typography>
        <Box sx={{ width: 180, height: 10, background: 'linear-gradient(90deg, #be123c, #fff 50%, #155e75)' }} />
        <Typography variant="caption">+1 correlation</Typography>
      </Stack>
    </Paper>
  )
}

function AxisSelect({ label, value, components, onChange }: { label: string; value: string; components: string[]; onChange: (value: string) => void }) {
  return (
    <FormControl size="small" sx={{ minWidth: 100 }}>
      <InputLabel>{label}</InputLabel>
      <Select label={label} value={value} onChange={(event) => onChange(event.target.value)}>
        {components.map((component) => <MenuItem key={component} value={component}>{component}</MenuItem>)}
      </Select>
    </FormControl>
  )
}

function VarianceChart({ components }: { components: Array<{ component: string; explained_variance_ratio: number }> }) {
  const maximum = Math.max(...components.map((component) => component.explained_variance_ratio), 0.01)
  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Typography variant="h5" fontWeight={700}>Explained variance</Typography>
      <Stack direction="row" spacing={1.5} alignItems="flex-end" sx={{ height: 260, mt: 3 }}>
        {components.map((component) => (
          <Stack key={component.component} alignItems="center" justifyContent="flex-end" sx={{ flex: 1, height: '100%' }}>
            <Typography variant="caption" fontWeight={700}>{(component.explained_variance_ratio * 100).toFixed(1)}%</Typography>
            <Box sx={{ width: 'min(56px, 80%)', height: `${(component.explained_variance_ratio / maximum) * 190}px`, minHeight: 2, bgcolor: 'primary.main', borderRadius: '5px 5px 0 0', mt: 0.5 }} />
            <Typography variant="body2" mt={1}>{component.component}</Typography>
          </Stack>
        ))}
      </Stack>
    </Paper>
  )
}
