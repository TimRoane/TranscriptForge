import ArrowBackRoundedIcon from '@mui/icons-material/ArrowBackRounded'
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded'
import LockRoundedIcon from '@mui/icons-material/LockRounded'
import PlayArrowRoundedIcon from '@mui/icons-material/PlayArrowRounded'
import StopCircleRoundedIcon from '@mui/icons-material/StopCircleRounded'
import {
  Alert,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  Link,
  Paper,
  Stack,
  Typography,
} from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom'

import {
  type StudyAssignment,
  artifactDownloadUrl,
  cancelRun,
  cloneAnalyticalStudy,
  fetchAnalyticalStudy,
  fetchAnalyticalStudyResults,
  lockAnalyticalStudy,
  runAnalyticalStudy,
  updateAnalyticalStudy,
} from '../api/client'
import { ErrorState, LoadingState } from '../components/ApiState'
import { StudyAssignmentTable } from '../components/StudyAssignmentTable'

const editableStatuses = new Set(['DRAFT', 'DESIGN_VALID', 'DESIGN_INVALID'])

function statusColor(status: string): 'default' | 'success' | 'error' | 'warning' | 'secondary' {
  if (status === 'SUCCEEDED' || status === 'DESIGN_VALID' || status === 'PASS') return 'success'
  if (status === 'FAILED' || status === 'DESIGN_INVALID' || status === 'FAIL') return 'error'
  if (status === 'LOCKED') return 'secondary'
  if (['QUEUED', 'RUNNING', 'INDETERMINATE'].includes(status)) return 'warning'
  return 'default'
}

function metric(value: unknown, digits = 3) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : 'Not estimable'
}

export function StudyPage() {
  const { studyId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const study = useQuery({ queryKey: ['study', studyId], queryFn: ({ signal }) => fetchAnalyticalStudy(studyId, signal), enabled: !!studyId, refetchInterval: (query) => ['QUEUED', 'RUNNING'].includes(query.state.data?.status || '') ? 3000 : false })
  const results = useQuery({ queryKey: ['study-results', studyId], queryFn: ({ signal }) => fetchAnalyticalStudyResults(studyId, signal), enabled: !!studyId, refetchInterval: (query) => ['QUEUED', 'RUNNING'].includes(query.state.data?.status || '') ? 3000 : false })
  const [assignments, setAssignments] = useState<StudyAssignment[]>([])

  useEffect(() => {
    if (study.data) setAssignments(study.data.assignments_json)
  }, [study.data])

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['study', studyId] }),
      queryClient.invalidateQueries({ queryKey: ['study-results', studyId] }),
      queryClient.invalidateQueries({ queryKey: ['assay-studies'] }),
      queryClient.invalidateQueries({ queryKey: ['assay-readiness'] }),
    ])
  }
  const save = useMutation({ mutationFn: () => updateAnalyticalStudy(studyId, { assignments }), onSuccess: refresh })
  const lock = useMutation({ mutationFn: () => lockAnalyticalStudy(studyId), onSuccess: refresh })
  const run = useMutation({ mutationFn: () => runAnalyticalStudy(studyId), onSuccess: refresh })
  const cancel = useMutation({ mutationFn: (runId: string) => cancelRun(runId), onSuccess: refresh })
  const clone = useMutation({ mutationFn: () => cloneAnalyticalStudy(studyId), onSuccess: (item) => navigate(`/studies/${item.id}`) })

  if (study.isPending || results.isPending) return <LoadingState label="Loading Analytical Study…" />
  if (study.isError || results.isError) return <ErrorState error={study.error || results.error} />
  const item = study.data
  const inputLimit = item.study_type === 'INPUT_DEGRADATION_LIMIT'
  const pairedBridge = item.study_type === 'PAIRED_BRIDGING'
  const robustness = item.study_type === 'ROBUSTNESS_INTERFERENCE'
  const validation = item.design_validation_json
  const editable = editableStatuses.has(item.status)
  const summary = results.data.summary
  const error = save.error || lock.error || run.error || cancel.error || clone.error
  const precision = summary?.precision || {}
  const variance = summary?.variance_components || {}
  const metricCards: Array<[string, unknown]> = [
    ['ICC', variance.icc],
    ['Repeatability SD', precision.repeatability_sd],
    ['Reproducibility SD', precision.reproducibility_sd],
    ['Call agreement', summary?.agreement?.categorical_agreement],
  ]

  return <Stack spacing={4}>
    <Link component={RouterLink} to={`/assay-development/${item.assay_project_id}`} underline="hover" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, width: 'fit-content' }}><ArrowBackRoundedIcon fontSize="small" /> Guided assay workspace</Link>
    <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" gap={2}>
      <div><Typography variant="overline" color="secondary.main" fontWeight={750}>Post-lock Analytical Study · revision {item.current_revision}</Typography><Typography variant="h3" fontWeight={760}>{item.name}</Typography><Typography color="text.secondary" mt={1}>{item.objective}</Typography></div>
      <Chip label={item.status.replaceAll('_', ' ')} color={statusColor(item.status)} sx={{ alignSelf: 'flex-start' }} />
    </Stack>

    <Alert severity="info" icon={<LockRoundedIcon />}>Model {item.model_id} is a frozen endpoint. This study applies it without feature selection, fitting, calibration, threshold tuning, or retraining.</Alert>
    {item.status === 'DESIGN_INVALID' && <Alert severity="error">Design blocked. Repair every blocking finding and save before locking.</Alert>}
    {item.status === 'LOCKED' && <Alert severity="success">The StudySpec, assignments, criteria, model manifest, and validation bundle input are frozen. You can now run this exact revision.</Alert>}
    {['QUEUED', 'RUNNING'].includes(item.status) && <Alert severity="info">The frozen study is {item.status.toLowerCase()}. This page refreshes automatically.</Alert>}
    {error && <ErrorState error={error} />}

    <Paper variant="outlined" sx={{ p: 3 }}><Grid container spacing={2}>
      <Grid item xs={12} md={4}><Typography variant="overline" fontWeight={750}>Locked model</Typography><Typography fontFamily="monospace" variant="body2">{item.model_id}</Typography></Grid>
      <Grid item xs={12} md={4}><Typography variant="overline" fontWeight={750}>Validation bundle input</Typography><Typography fontFamily="monospace" variant="body2">{item.prepared_dataset_id}</Typography></Grid>
      <Grid item xs={12} md={4}><Typography variant="overline" fontWeight={750}>Immutable hashes</Typography><Typography fontFamily="monospace" variant="caption" display="block">Spec {item.study_spec_sha256 || 'not locked'}</Typography><Typography fontFamily="monospace" variant="caption">Assignments {item.assignments_sha256 || 'not locked'}</Typography></Grid>
    </Grid></Paper>

    <div><Typography variant="h4" fontWeight={740}>{inputLimit ? 'Ordered paired-level design' : pairedBridge ? 'Paired bridge design' : robustness ? 'Challenge/reference paired design' : 'Repeated-measure design'}</Typography><Typography color="text.secondary" mt={0.5}>{inputLimit ? 'Every biological sample needs exactly one measurement at each ordered level, including the declared reference.' : pairedBridge ? 'Every biological sample needs exactly one reference and comparator measurement; bridge condition must not be confounded with run.' : robustness ? 'Every biological sample needs exactly one reference and challenge measurement; challenge must not be confounded with run.' : 'Every included biological sample needs repeated measurements. Declared factors must have multiple estimable levels without perfect confounding.'}</Typography></div>
    <StudyAssignmentTable assignments={assignments} editable={editable} template={inputLimit ? 'input_limit' : pairedBridge ? 'paired_bridge' : robustness ? 'robustness' : 'precision'} onChange={setAssignments} />
    {validation && <Paper variant="outlined" sx={{ p: 3 }}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}><Chip label={validation.valid ? 'DESIGN VALID' : 'DESIGN BLOCKED'} color={validation.valid ? 'success' : 'error'} /><Typography>{validation.included_measurement_count} measurements · {validation.biological_sample_count} biological samples · rank {validation.design_matrix_rank}/{validation.design_matrix_columns}</Typography></Stack>
      <Stack spacing={1.5} mt={2}>{validation.errors.map((finding) => <Alert severity="error" key={finding.code}><Typography fontWeight={700}>{finding.message}</Typography><Typography variant="caption">{finding.code} · {JSON.stringify(finding.facts || {})}</Typography></Alert>)}{validation.warnings.map((finding) => <Alert severity="warning" key={finding.code}><Typography fontWeight={700}>{finding.message}</Typography><Typography variant="caption">{finding.code}</Typography></Alert>)}{validation.valid && !validation.warnings.length && <Alert severity="success">No blocking design findings or warnings.</Alert>}</Stack>
      <Typography variant="body2" mt={2}><strong>Factor levels:</strong> {Object.entries(validation.factor_levels).map(([factor, levels]) => `${factor} (${levels.join(', ')})`).join(' · ')}</Typography>
    </Paper>}

    <Paper variant="outlined" sx={{ p: 3 }}><Typography variant="h5" fontWeight={720}>Frozen criteria preview</Typography><Grid container spacing={2} mt={0}>{item.criteria_json.map((criterion) => <Grid item xs={12} md={6} key={criterion.key}><Card variant="outlined"><CardContent><Typography fontWeight={700}>{criterion.metric.replaceAll('_', ' ')}</Typography><Typography>{criterion.operator} {JSON.stringify(criterion.threshold)}</Typography><Typography variant="body2" color="text.secondary" mt={1}>{criterion.rationale}</Typography></CardContent></Card></Grid>)}</Grid></Paper>

    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
      {editable && <Button variant="outlined" color="secondary" disabled={save.isPending} onClick={() => save.mutate()}>Save assignments and revalidate</Button>}
      {editable && <Button variant="contained" color="secondary" startIcon={<LockRoundedIcon />} disabled={!validation?.valid || save.isPending || lock.isPending} onClick={() => lock.mutate()}>Lock study design and continue to run</Button>}
      {item.status === 'LOCKED' && <Button variant="contained" color="secondary" startIcon={<PlayArrowRoundedIcon />} disabled={run.isPending} onClick={() => run.mutate()}>Run locked validation study</Button>}
      {results.data.run_id && ['QUEUED', 'RUNNING'].includes(item.status) && <Button variant="outlined" color="error" startIcon={<StopCircleRoundedIcon />} disabled={cancel.isPending} onClick={() => cancel.mutate(results.data.run_id!)}>Cancel computation</Button>}
      {!editable && <Button variant="outlined" disabled={clone.isPending} onClick={() => clone.mutate()}>Clone as editable study</Button>}
    </Stack>

    {summary && <>
      <Divider />
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" gap={2}><div><Typography variant="overline" color="secondary.main" fontWeight={750}>Validation Bundle</Typography><Typography variant="h3" fontWeight={760}>{inputLimit ? 'Input/degradation limit evidence review' : pairedBridge ? 'Paired bridging evidence review' : robustness ? 'Robustness/interference evidence review' : 'Precision evidence review'}</Typography></div><Chip label={summary.overall_status} color={statusColor(summary.overall_status)} sx={{ alignSelf: 'flex-start', fontSize: 16, px: 1 }} /></Stack>
      <Alert severity="warning">Scientist decision required. The overall label does not replace review of every criterion, limitation, and measurement near the decision boundary.</Alert>
      {!inputLimit && !pairedBridge && !robustness && <Grid container spacing={2}>
        {metricCards.map(([label, value]) => <Grid item xs={12} sm={6} md={3} key={label}><Card variant="outlined" sx={{ height: '100%' }}><CardContent><Typography variant="overline" color="secondary.main" fontWeight={750}>{label}</Typography><Typography variant="h4" fontWeight={760} mt={1}>{metric(value)}</Typography></CardContent></Card></Grid>)}
      </Grid>}
      {inputLimit && summary.input_degradation && <Paper variant="outlined" sx={{ p: 3 }}><Typography variant="h5" fontWeight={720}>Ordered-level evidence</Typography><Alert severity="warning" sx={{ mt: 1.5 }}>Candidate lowest tested level: {summary.input_degradation.candidate_lowest_tested_level ?? 'none'}. This does not automatically establish a clinical LoD.</Alert><Grid container spacing={2} mt={0}>{summary.input_degradation.levels.map((level, index) => <Grid item xs={12} sm={6} md={4} key={index}><Card variant="outlined"><CardContent><Typography variant="h5" fontWeight={750}>Level {String(level.input_level)}</Typography><Typography variant="body2">Mean score difference: {metric(level.mean_score_difference)}</Typography><Typography variant="body2">Call agreement: {metric(level.call_agreement_to_reference)}</Typography><Typography variant="body2">QC failure rate: {metric(level.qc_failure_rate)}</Typography></CardContent></Card></Grid>)}</Grid><Typography variant="body2" mt={2}>{summary.input_degradation.candidate_interpretation}</Typography></Paper>}
      {pairedBridge && summary.paired_bridging && <Paper variant="outlined" sx={{ p: 3 }}><Typography variant="h5" fontWeight={720}>Paired equivalence evidence</Typography><Alert severity="warning" sx={{ mt: 1.5 }}>Correlation is descriptive and cannot pass equivalence on its own.</Alert><Grid container spacing={2} mt={0}>{([['Paired bias', summary.paired_bridging.paired_bias], ['Profile correlation', summary.paired_bridging.profile_correlation], ['Call agreement', summary.paired_bridging.categorical_agreement], ['Discordance rate', summary.paired_bridging.discordance_rate]] as const).map(([label, value]) => <Grid item xs={12} sm={6} md={3} key={label}><Card variant="outlined"><CardContent><Typography variant="overline">{label}</Typography><Typography variant="h5">{metric(value)}</Typography></CardContent></Card></Grid>)}</Grid><Typography mt={2}>TOST interval rule with margin ±{summary.paired_bridging.tost_equivalence.margin}: <strong>{summary.paired_bridging.tost_equivalence.passed ? 'within margin' : 'not within margin'}</strong>.</Typography></Paper>}
      {robustness && summary.robustness_interference && <Paper variant="outlined" sx={{ p: 3 }}><Typography variant="h5" fontWeight={720}>Paired challenge evidence</Typography><Alert severity="warning" sx={{ mt: 1.5 }}>Technical challenge effects do not establish biological specificity.</Alert><Grid container spacing={2} mt={0}>{([['Mean challenge effect', summary.robustness_interference.mean_challenge_effect], ['Call change rate', summary.robustness_interference.call_change_rate], ['QC failure rate', summary.robustness_interference.qc_failure_rate], ['Tested pairs', summary.robustness_interference.pair_count]] as const).map(([label, value]) => <Grid item xs={12} sm={6} md={3} key={label}><Card variant="outlined"><CardContent><Typography variant="overline">{label}</Typography><Typography variant="h5">{metric(value)}</Typography></CardContent></Card></Grid>)}</Grid><Typography mt={2}>Challenge-effect interval with margin ±{summary.robustness_interference.maximum_effect_margin}: <strong>{summary.robustness_interference.effect_within_margin ? 'within margin' : 'not within margin'}</strong>.</Typography></Paper>}
      <Paper variant="outlined" sx={{ p: 3 }}><Typography variant="h5" fontWeight={720}>Acceptance criteria</Typography><Stack spacing={2} mt={2}>{summary.acceptance_results.criteria.map((criterion) => <Card variant="outlined" key={criterion.key}><CardContent><Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={1}><div><Typography fontWeight={720}>{criterion.metric.replaceAll('_', ' ')}</Typography><Typography variant="body2">Observed {typeof criterion.observed === 'number' ? metric(criterion.observed) : JSON.stringify(criterion.observed)} · required {criterion.operator} {JSON.stringify(criterion.threshold)}</Typography></div><Chip label={criterion.status} color={statusColor(criterion.status)} /></Stack><Typography variant="body2" color="text.secondary" mt={1}>{criterion.rationale}</Typography><Typography variant="caption">Population: {criterion.population}</Typography></CardContent></Card>)}</Stack></Paper>
      {!inputLimit && !pairedBridge && !robustness && <Paper variant="outlined" sx={{ p: 3 }}><Typography variant="h5" fontWeight={720}>Decision-boundary stability</Typography><Typography mt={1}>Decision threshold {summary.threshold_stability.decision_threshold}; proximity band ±{summary.threshold_stability.proximity_band}. {summary.threshold_stability.near_threshold_count} measurement(s) are near the boundary.</Typography>{summary.threshold_stability.near_threshold_measurement_ids.length > 0 && <Typography fontFamily="monospace" variant="body2" mt={1}>{summary.threshold_stability.near_threshold_measurement_ids.join(', ')}</Typography>}</Paper>}
      <Paper variant="outlined" sx={{ p: 3 }}><Typography variant="h5" fontWeight={720}>Finding and limitations</Typography><Typography mt={1}>{summary.finding}</Typography><Stack component="ul" mt={1}>{summary.limitations.map((limitation) => <Typography component="li" key={limitation}>{limitation}</Typography>)}</Stack><Alert severity="success" sx={{ mt: 2 }}>Execution provenance confirms model_retrained = {String(summary.model_retrained)}.</Alert></Paper>
      <div><Typography variant="h5" fontWeight={720}>Validation evidence artifacts</Typography><Grid container spacing={1.5} mt={0.5}>{results.data.artifacts.map((artifact) => <Grid item xs={12} sm={6} key={artifact.id}><Button component="a" href={artifactDownloadUrl(artifact.id)} fullWidth variant={artifact.artifact_type === 'validation_bundle' ? 'contained' : 'outlined'} color="secondary" startIcon={<DownloadRoundedIcon />} sx={{ justifyContent: 'flex-start' }}>{artifact.title}</Button></Grid>)}</Grid></div>
    </>}
  </Stack>
}
