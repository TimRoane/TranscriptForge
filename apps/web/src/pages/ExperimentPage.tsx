import ArrowBackRoundedIcon from '@mui/icons-material/ArrowBackRounded'
import CheckCircleRoundedIcon from '@mui/icons-material/CheckCircleRounded'
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded'
import LockRoundedIcon from '@mui/icons-material/LockRounded'
import PlayArrowRoundedIcon from '@mui/icons-material/PlayArrowRounded'
import StopCircleRoundedIcon from '@mui/icons-material/StopCircleRounded'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Grid,
  Link,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom'

import {
  type ExperimentAssignment,
  type Recommendation,
  acceptDevelopmentExperimentFollowUp,
  artifactDownloadUrl,
  cancelRun,
  cloneDevelopmentExperiment,
  experimentWetLabPackageUrl,
  fetchDevelopmentExperiment,
  fetchDevelopmentExperimentRecommendations,
  fetchDevelopmentExperimentResults,
  lockDevelopmentExperiment,
  resolveRecommendation,
  runDevelopmentExperiment,
  updateDevelopmentExperiment,
} from '../api/client'
import { ErrorState, LoadingState } from '../components/ApiState'
import { ExperimentAssignmentTable } from '../components/ExperimentAssignmentTable'

const editableStatuses = new Set(['DRAFT', 'DESIGN_VALID', 'DESIGN_INVALID'])
type RecommendationMutationResult =
  | Awaited<ReturnType<typeof acceptDevelopmentExperimentFollowUp>>
  | Awaited<ReturnType<typeof resolveRecommendation>>

function statusColor(status: string): 'default' | 'success' | 'error' | 'warning' | 'secondary' {
  if (status === 'SUCCEEDED' || status === 'DESIGN_VALID') return 'success'
  if (status === 'FAILED' || status === 'DESIGN_INVALID') return 'error'
  if (status === 'LOCKED_FOR_EXECUTION') return 'secondary'
  if (['QUEUED', 'RUNNING'].includes(status)) return 'warning'
  return 'default'
}

export function ExperimentPage() {
  const { experimentId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const experiment = useQuery({ queryKey: ['experiment', experimentId], queryFn: ({ signal }) => fetchDevelopmentExperiment(experimentId, signal), enabled: !!experimentId, refetchInterval: (query) => ['QUEUED', 'RUNNING'].includes(query.state.data?.status || '') ? 3000 : false })
  const results = useQuery({ queryKey: ['experiment-results', experimentId], queryFn: ({ signal }) => fetchDevelopmentExperimentResults(experimentId, signal), enabled: !!experimentId, refetchInterval: (query) => ['QUEUED', 'RUNNING'].includes(query.state.data?.status || '') ? 3000 : false })
  const recommendations = useQuery({ queryKey: ['experiment-recommendations', experimentId], queryFn: ({ signal }) => fetchDevelopmentExperimentRecommendations(experimentId, signal), enabled: !!experimentId })
  const [assignments, setAssignments] = useState<ExperimentAssignment[]>([])
  const [referenceLevel, setReferenceLevel] = useState(0)
  const [referenceCondition, setReferenceCondition] = useState('')
  const [comparatorCondition, setComparatorCondition] = useState('')
  const [decisionTarget, setDecisionTarget] = useState<Recommendation | null>(null)
  const [decision, setDecision] = useState<'accept' | 'reject' | 'modify'>('accept')
  const [rationale, setRationale] = useState('')

  useEffect(() => {
    if (!experiment.data) return
    setAssignments(experiment.data.assignments)
    const analysisPlan = experiment.data.experiment_spec.analysis_plan as { reference_level?: number; reference_condition?: string; comparator_condition?: string } | undefined
    setReferenceLevel(Number(analysisPlan?.reference_level || 0))
    setReferenceCondition(analysisPlan?.reference_condition || '')
    setComparatorCondition(analysisPlan?.comparator_condition || '')
  }, [experiment.data])

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] }),
      queryClient.invalidateQueries({ queryKey: ['experiment-results', experimentId] }),
      queryClient.invalidateQueries({ queryKey: ['experiment-recommendations', experimentId] }),
      queryClient.invalidateQueries({ queryKey: ['assay-experiments'] }),
    ])
  }
  const pairedCondition = experiment.data?.experiment_type === 'PAIRED_CONDITION_COMPARISON'
  const multifactor = experiment.data?.experiment_type === 'MULTIFACTOR_OPTIMIZATION'
  const technicalFeasibility = experiment.data?.experiment_type === 'TECHNICAL_FEASIBILITY'
  const save = useMutation({ mutationFn: () => updateDevelopmentExperiment(experimentId, technicalFeasibility ? { assignments } : pairedCondition ? { assignments, reference_condition: referenceCondition, comparator_condition: comparatorCondition } : multifactor ? { assignments } : { assignments, reference_level: referenceLevel }), onSuccess: refresh })
  const lock = useMutation({ mutationFn: () => lockDevelopmentExperiment(experimentId), onSuccess: refresh })
  const run = useMutation({ mutationFn: () => runDevelopmentExperiment(experimentId), onSuccess: refresh })
  const cancel = useMutation({ mutationFn: (runId: string) => cancelRun(runId), onSuccess: refresh })
  const clone = useMutation({ mutationFn: () => cloneDevelopmentExperiment(experimentId), onSuccess: (item) => navigate(`/experiments/${item.id}`) })
  const resolve = useMutation<RecommendationMutationResult, Error>({
    mutationFn: async () => decision === 'accept'
      ? await acceptDevelopmentExperimentFollowUp(experimentId, decisionTarget!.id, rationale)
      : await resolveRecommendation(decisionTarget!.id, decision, { rationale, modified_action: decision === 'modify' ? { ...decisionTarget!.proposed_action, scientist_note: rationale } : undefined }),
    onSuccess: async (result) => {
      setDecisionTarget(null)
      setRationale('')
      if ('experiment_type' in result) navigate(`/experiments/${result.id}`)
      else await refresh()
    },
  })

  const balance = useMemo(() => {
    const counts = new Map<string, number>()
    for (const row of assignments.filter((item) => item.include)) {
      const key = technicalFeasibility
        ? `${row.specimen_group || 'all specimens'} · ${row.run || row.sequencing_run || 'unmapped run'}`
        : pairedCondition
        ? `${row.condition || 'unmapped condition'} · ${row.run || 'unmapped run'}`
        : multifactor
          ? `${row.extraction_method || 'unmapped method'} · ${row.input_ng || '?'} ng · ${row.run || 'unmapped run'}`
          : `${row.input_ng || '?'} ng · ${row.sequencing_run || 'unmapped run'}`
      counts.set(key, (counts.get(key) || 0) + 1)
    }
    return [...counts.entries()]
  }, [assignments, technicalFeasibility, pairedCondition, multifactor])

  if (experiment.isPending || results.isPending) return <LoadingState label="Loading Development Experiment…" />
  if (experiment.isError || results.isError) return <ErrorState error={experiment.error || results.error} />
  const item = experiment.data
  const validation = item.design_validation
  const editable = editableStatuses.has(item.status)
  const summary = results.data.decision_summary
  const mutationError = save.error || lock.error || run.error || cancel.error || clone.error

  return <Stack spacing={4}>
    <Link component={RouterLink} to={`/assay-development/${item.assay_project_id}`} underline="hover" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, width: 'fit-content' }}><ArrowBackRoundedIcon fontSize="small" /> Guided assay workspace</Link>
    <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" gap={2}>
      <div><Typography variant="overline" color="secondary.main" fontWeight={750}>Development Experiment · revision {item.current_revision}</Typography><Typography variant="h3" fontWeight={760}>{item.name}</Typography><Typography color="text.secondary" mt={1}>{item.objective}</Typography></div>
      <Chip label={item.status.replaceAll('_', ' ')} color={statusColor(item.status)} sx={{ alignSelf: 'flex-start' }} />
    </Stack>

    {item.status === 'DESIGN_INVALID' && <Alert severity="error">Design blocked. Correct every blocking finding below, save, and revalidate before locking.</Alert>}
    {item.status === 'LOCKED_FOR_EXECUTION' && <Alert severity="info" icon={<LockRoundedIcon />}>This revision is immutable and ready to run. Clone it to change assignments or endpoints.</Alert>}
    {['QUEUED', 'RUNNING'].includes(item.status) && <Alert severity="info">Computation is {item.status.toLowerCase()}. This page refreshes automatically; the frozen revision and checksums remain unchanged.</Alert>}
    {mutationError && <ErrorState error={mutationError} />}

    <Paper variant="outlined" sx={{ p: 3 }}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={3} alignItems={{ md: 'center' }}>
        {technicalFeasibility ? <Typography><strong>Evidence mode:</strong> exploratory technical feasibility</Typography> : pairedCondition ? <>
          <TextField label="Reference condition" value={referenceCondition} disabled={!editable} onChange={(event) => setReferenceCondition(event.target.value)} sx={{ width: 220 }} />
          <TextField label="Comparator condition" value={comparatorCondition} disabled={!editable} onChange={(event) => setComparatorCondition(event.target.value)} sx={{ width: 220 }} />
        </> : multifactor ? <Typography><strong>Frozen factors:</strong> extraction method × input, with repeated-sample and run blocks</Typography> : <TextField type="number" label="Reference input (ng)" value={referenceLevel || ''} disabled={!editable} onChange={(event) => setReferenceLevel(Number(event.target.value))} sx={{ width: 220 }} />}
        <Box flex={1}><Typography variant="overline" fontWeight={750}>Frozen input lineage</Typography><Typography variant="body2">Prepared dataset {item.prepared_dataset_id}</Typography>{item.experiment_spec_sha256 && <Typography variant="caption" fontFamily="monospace">Spec SHA-256 {item.experiment_spec_sha256}</Typography>}</Box>
        <Button component="a" href={experimentWetLabPackageUrl(item.id)} startIcon={<DownloadRoundedIcon />}>Wet-lab package</Button>
      </Stack>
    </Paper>

    <div><Typography variant="h4" fontWeight={740}>Assignment and balance review</Typography><Typography color="text.secondary" mt={0.5}>{technicalFeasibility ? 'Review explicit specimen, run, RNA-quality, and failure metadata; absent fields remain visible limitations.' : <>A perfect {pairedCondition ? 'condition-by-factor' : multifactor ? 'factor-by-run' : 'input-by-run'} alignment is a blocker. Imbalance that remains estimable is reported as a warning.</>}</Typography></div>
    <ExperimentAssignmentTable assignments={assignments} editable={editable} template={technicalFeasibility ? 'technical_feasibility' : pairedCondition ? 'paired_condition' : multifactor ? 'multifactor' : 'input_degradation'} onChange={setAssignments} />
    <Paper variant="outlined" sx={{ p: 2.5 }}><Typography variant="h6" fontWeight={700}>Factor balance: {technicalFeasibility ? 'specimen group × run' : pairedCondition ? 'condition × run' : multifactor ? 'method × input × run' : 'input × sequencing run'}</Typography><Stack direction="row" gap={1} flexWrap="wrap" mt={1.5}>{balance.map(([cell, count]) => <Chip key={cell} label={`${cell}: n=${count}`} variant="outlined" />)}</Stack></Paper>

    {validation && <Paper variant="outlined" sx={{ p: 3 }}>
      <Stack direction="row" spacing={1} alignItems="center"><Chip label={validation.valid ? 'DESIGN VALID' : 'DESIGN BLOCKED'} color={validation.valid ? 'success' : 'error'} /><Typography>{validation.included_measurement_count} measurements · {validation.biological_sample_count} biological samples · {technicalFeasibility ? `${(validation.specimen_groups || []).length} specimen group(s) · ${(validation.run_levels || []).length} run(s)` : pairedCondition ? `${validation.complete_pair_count || 0} complete pairs · ${(validation.conditions || []).join(' vs ')}` : multifactor ? `rank ${validation.design_matrix_rank}/${validation.design_matrix_columns} · residual df ${validation.residual_degrees_of_freedom}` : `levels ${(validation.input_levels || []).join(', ')} ng`}</Typography></Stack>
      <Stack spacing={2} divider={<Divider flexItem />} mt={2}>{validation.findings.length === 0 ? <Alert severity="success" icon={<CheckCircleRoundedIcon />}>No blocking errors or warnings were found.</Alert> : validation.findings.map((finding) => <Alert key={finding.code} severity={finding.severity === 'ERROR' ? 'error' : finding.severity === 'WARNING' ? 'warning' : 'info'}><Typography fontWeight={700}>{finding.message}</Typography><Typography variant="body2" mt={0.5}>{finding.recommendation}</Typography><Typography variant="caption">{finding.code} · {JSON.stringify(finding.facts)}</Typography></Alert>)}</Stack>
    </Paper>}

    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
      {editable && <Button variant="outlined" color="secondary" disabled={save.isPending} onClick={() => save.mutate()}>Save changes and revalidate</Button>}
      {editable && <Button variant="contained" color="secondary" startIcon={<LockRoundedIcon />} disabled={!validation?.valid || save.isPending || lock.isPending} onClick={() => lock.mutate()}>Lock revision and continue to run</Button>}
      {item.status === 'LOCKED_FOR_EXECUTION' && <Button variant="contained" color="secondary" startIcon={<PlayArrowRoundedIcon />} disabled={run.isPending} onClick={() => run.mutate()}>Run locked experiment</Button>}
      {results.data.run_id && ['QUEUED', 'RUNNING'].includes(item.status) && <Button variant="outlined" color="error" startIcon={<StopCircleRoundedIcon />} disabled={cancel.isPending} onClick={() => cancel.mutate(results.data.run_id!)}>Cancel computation</Button>}
      {!editable && <Button variant="outlined" disabled={clone.isPending} onClick={() => clone.mutate()}>Clone as editable draft</Button>}
    </Stack>

    {summary && <>
      <Divider />
      <div><Typography variant="overline" color="secondary.main" fontWeight={750}>Development Evidence Bundle</Typography><Typography variant="h3" fontWeight={760}>Evidence review</Typography></div>
      <Grid container spacing={2}>
        {([['Question', summary.question], ['Finding', summary.finding], ['Evidence', `${summary.condition_results.length} tested condition level(s), with checksummed primary results and measurement-level endpoints.`], ['Limitations', summary.limitations.join(' ')] ] as const).map(([title, body]) => <Grid item xs={12} md={6} key={title}><Card variant="outlined" sx={{ height: '100%' }}><CardContent><Typography variant="overline" color="secondary.main" fontWeight={750}>{title}</Typography><Typography mt={1}>{body}</Typography></CardContent></Card></Grid>)}
      </Grid>
      <Paper variant="outlined" sx={{ p: 3 }}><Typography variant="h5" fontWeight={720}>{technicalFeasibility ? 'Technical feasibility evidence' : 'Condition evidence'}</Typography><Grid container spacing={2} mt={0}>{summary.condition_results.map((condition, index) => <Grid item xs={12} sm={6} md={pairedCondition ? 12 : 4} key={index}><Card variant="outlined"><CardContent>{technicalFeasibility ? <><Typography variant="h5" fontWeight={750}>{String(condition.group)}</Typography><Typography variant="body2">Successful measurements: {Number(condition.successful_measurements)} of {Number(condition.measurement_count)}</Typography><Typography variant="body2">Technical success rate: {(Number(condition.technical_success_rate) * 100).toFixed(1)}%</Typography><Typography variant="body2">Median detected genes: {Number(condition.median_detected_genes).toFixed(0)}</Typography></> : pairedCondition ? <><Typography variant="h5" fontWeight={750}>{String(condition.comparator_condition)} versus {String(condition.reference_condition)}</Typography><Grid container spacing={1.5} mt={0.5}><Grid item xs={6} md={3}><Typography variant="body2">Complete pairs</Typography><Typography variant="h6">{Number(condition.pair_count)}</Typography></Grid><Grid item xs={6} md={3}><Typography variant="body2">Mean paired difference</Typography><Typography variant="h6">{Number(condition.mean_paired_difference).toFixed(3)}</Typography></Grid><Grid item xs={6} md={3}><Typography variant="body2">Mean profile correlation</Typography><Typography variant="h6">{Number(condition.mean_profile_correlation).toFixed(3)}</Typography></Grid><Grid item xs={6} md={3}><Typography variant="body2">Failure-rate difference</Typography><Typography variant="h6">{Number(condition.failure_rate_difference).toFixed(3)}</Typography></Grid></Grid></> : multifactor ? <><Typography variant="h5" fontWeight={750}>{String(condition.extraction_method)} · {Number(condition.input_ng)} ng</Typography><Typography variant="body2">Measurements: {Number(condition.measurement_count)}</Typography><Typography variant="body2">Mean expression: {Number(condition.mean_expression).toFixed(3)}</Typography></> : <><Typography variant="h5" fontWeight={750}>{Number(condition.input_ng)} ng</Typography><Typography variant="body2">Measurements: {Number(condition.measurement_count)}</Typography><Typography variant="body2">Mean paired correlation: {Number(condition.mean_profile_correlation).toFixed(3)}</Typography><Chip size="small" sx={{ mt: 1 }} label={condition.descriptive_stability_indicator ? 'Descriptive indicator met' : 'Indicator not met'} color={condition.descriptive_stability_indicator ? 'success' : 'warning'} /></>}</CardContent></Card></Grid>)}</Grid><Alert severity="warning" sx={{ mt: 2 }}>{technicalFeasibility ? 'Exploratory technical evidence only. Review success, RNA quantity and quality, expression suitability, and failure patterns together; this does not establish a clinical specimen requirement.' : pairedCondition ? 'Exploratory multi-endpoint evidence only. Do not rank a condition from one metric; review bias, uncertainty, failures, concordance, discordance, and quality interaction together.' : multifactor ? 'Exploratory constrained-model evidence only. Review effect intervals, repeated-sample variance, cell support, and interactions together before selecting confirmation conditions.' : 'Exploratory criteria only. The 0.95 profile-stability indicator is descriptive; this result does not establish a clinical LoD or final minimum input.'}</Alert></Paper>
      <Paper variant="outlined" sx={{ p: 3 }}><Typography variant="overline" color="secondary.main" fontWeight={750}>Scientist decision required</Typography><Typography variant="h5" fontWeight={720}>Recommended next action</Typography>{recommendations.data?.filter((recommendation) => recommendation.status === 'OPEN').map((recommendation) => <Box key={recommendation.id} mt={2}><Typography fontWeight={700}>{recommendation.title}</Typography><Typography>{recommendation.summary}</Typography><Typography variant="body2" color="text.secondary" mt={1}>{recommendation.why}</Typography><Stack direction="row" spacing={1} mt={2}><Button variant="contained" color="secondary" onClick={() => { setDecision('accept'); setDecisionTarget(recommendation) }}>Accept</Button><Button onClick={() => { setDecision('modify'); setDecisionTarget(recommendation) }}>Modify</Button><Button color="error" onClick={() => { setDecision('reject'); setDecisionTarget(recommendation) }}>Reject or defer</Button></Stack></Box>)}</Paper>
      <div><Typography variant="h5" fontWeight={720}>Evidence artifacts</Typography><Grid container spacing={1.5} mt={0.5}>{results.data.artifacts.map((artifact) => <Grid item xs={12} sm={6} key={artifact.id}><Button component="a" href={artifactDownloadUrl(artifact.id)} fullWidth variant="outlined" startIcon={<DownloadRoundedIcon />} sx={{ justifyContent: 'flex-start' }}>{artifact.title}</Button></Grid>)}</Grid></div>
    </>}

    <Dialog open={decisionTarget !== null} onClose={() => setDecisionTarget(null)} fullWidth maxWidth="sm"><DialogTitle>{decision === 'accept' ? 'Accept and create follow-up draft' : decision === 'modify' ? 'Modify recommendation' : 'Reject or defer recommendation'}</DialogTitle><DialogContent><Stack spacing={2} mt={1}><Alert severity="info">This records a scientist-controlled decision and creates an editable follow-up draft. It does not launch the follow-up.</Alert><Typography>{decisionTarget?.title}</Typography><TextField required multiline minRows={3} label="Scientist rationale" value={rationale} onChange={(event) => setRationale(event.target.value)} />{resolve.isError && <ErrorState error={resolve.error} />}</Stack></DialogContent><DialogActions><Button onClick={() => setDecisionTarget(null)}>Cancel</Button><Button variant="contained" color="secondary" disabled={!rationale.trim() || resolve.isPending} onClick={() => resolve.mutate()}>{decision === 'accept' ? 'Accept and create draft' : 'Record decision'}</Button></DialogActions></Dialog>
  </Stack>
}
