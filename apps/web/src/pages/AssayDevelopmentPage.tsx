import ArrowBackRoundedIcon from '@mui/icons-material/ArrowBackRounded'
import CheckCircleRoundedIcon from '@mui/icons-material/CheckCircleRounded'
import ErrorOutlineRoundedIcon from '@mui/icons-material/ErrorOutlineRounded'
import HelpOutlineRoundedIcon from '@mui/icons-material/HelpOutlineRounded'
import WarningAmberRoundedIcon from '@mui/icons-material/WarningAmberRounded'
import {
  Alert,
  Button,
  Card,
  CardActions,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Grid,
  Link,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom'

import {
  type AssayLifecycleStage,
  type Recommendation,
  createScientificQuestion,
  fetchAssayDecisions,
  fetchAssayProject,
  fetchAssayReadiness,
  fetchAnalyticalStudies,
  fetchDevelopmentExperiments,
  fetchGuidanceResults,
  fetchQuestionCatalog,
  fetchRecommendations,
  fetchScientificQuestions,
  recordStageDecision,
  resolveRecommendation,
  updateAssayProject,
} from '../api/client'
import { ErrorState, LoadingState } from '../components/ApiState'

const stages: AssayLifecycleStage[] = ['DEFINE', 'FEASIBILITY', 'EXPLORE', 'OPTIMIZE', 'DEVELOP', 'LOCK', 'VALIDATE', 'REPORT']

const requirementColor = {
  BLOCKER: 'error',
  STRONGLY_RECOMMENDED: 'warning',
  RECOMMENDED: 'secondary',
  OPTIONAL: 'info',
  NOT_RECOMMENDED: 'default',
} as const

function EvidenceItems({ title, items, kind }: { title: string; items: Array<{ rule_id: string; conclusion: string; suggested_action: string; facts: Record<string, unknown> }>; kind: 'ready' | 'missing' | 'blocker' | 'warning' }) {
  const icon = kind === 'ready' ? <CheckCircleRoundedIcon color="success" /> : kind === 'blocker' ? <ErrorOutlineRoundedIcon color="error" /> : <WarningAmberRoundedIcon color="warning" />
  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      <CardContent>
        <Stack direction="row" spacing={1} alignItems="center">{icon}<Typography variant="h6" fontWeight={700}>{title}</Typography></Stack>
        {items.length === 0 ? <Typography color="text.secondary" mt={2}>None identified.</Typography> : (
          <Stack spacing={2} mt={2} divider={<Divider flexItem />}>
            {items.map((item) => <div key={item.rule_id}>
              <Typography fontWeight={650}>{item.conclusion}</Typography>
              <Typography variant="body2" color="text.secondary" mt={0.5}>{item.suggested_action}</Typography>
              <Typography variant="caption" color="text.secondary">Rule {item.rule_id} · Facts {JSON.stringify(item.facts)}</Typography>
            </div>)}
          </Stack>
        )}
      </CardContent>
    </Card>
  )
}

export function AssayDevelopmentPage() {
  const { assayProjectId = '' } = useParams()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [questionOpen, setQuestionOpen] = useState(false)
  const [questionKey, setQuestionKey] = useState('')
  const [formalQuestion, setFormalQuestion] = useState('')
  const [contextOpen, setContextOpen] = useState(false)
  const [contextDraft, setContextDraft] = useState({ proposed_purpose: '', specimen_type: '', biological_context: '', proposed_output: '' })
  const [decisionTarget, setDecisionTarget] = useState<Recommendation | null>(null)
  const [decisionKind, setDecisionKind] = useState<'accept' | 'reject'>('accept')
  const [rationale, setRationale] = useState('')
  const [notice, setNotice] = useState<string | null>(null)

  const assay = useQuery({ queryKey: ['assay-project', assayProjectId], queryFn: ({ signal }) => fetchAssayProject(assayProjectId, signal), enabled: !!assayProjectId })
  const readiness = useQuery({ queryKey: ['assay-readiness', assayProjectId], queryFn: ({ signal }) => fetchAssayReadiness(assayProjectId, signal), enabled: !!assayProjectId })
  const recommendations = useQuery({ queryKey: ['assay-recommendations', assayProjectId], queryFn: ({ signal }) => fetchRecommendations(assayProjectId, signal), enabled: !!assayProjectId })
  const questions = useQuery({ queryKey: ['assay-questions', assayProjectId], queryFn: ({ signal }) => fetchScientificQuestions(assayProjectId, signal), enabled: !!assayProjectId })
  const decisions = useQuery({ queryKey: ['assay-decisions', assayProjectId], queryFn: ({ signal }) => fetchAssayDecisions(assayProjectId, signal), enabled: !!assayProjectId })
  const experiments = useQuery({ queryKey: ['assay-experiments', assayProjectId], queryFn: ({ signal }) => fetchDevelopmentExperiments(assayProjectId, signal), enabled: !!assayProjectId })
  const studies = useQuery({ queryKey: ['assay-studies', assayProjectId], queryFn: ({ signal }) => fetchAnalyticalStudies(assayProjectId, signal), enabled: !!assayProjectId })
  const guidanceResults = useQuery({ queryKey: ['assay-guidance-results', assayProjectId], queryFn: ({ signal }) => fetchGuidanceResults(assayProjectId, signal), enabled: !!assayProjectId })
  const catalog = useQuery({ queryKey: ['scientific-question-catalog'], queryFn: ({ signal }) => fetchQuestionCatalog(signal) })
  const activeQuestion = questions.data?.find((item) => item.id === assay.data?.active_question_id)
  const selectedRoute = useMemo(() => catalog.data?.questions.find((item) => item.key === questionKey), [catalog.data, questionKey])

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['assay-project', assayProjectId] }),
      queryClient.invalidateQueries({ queryKey: ['assay-readiness', assayProjectId] }),
      queryClient.invalidateQueries({ queryKey: ['assay-recommendations', assayProjectId] }),
      queryClient.invalidateQueries({ queryKey: ['assay-questions', assayProjectId] }),
      queryClient.invalidateQueries({ queryKey: ['assay-decisions', assayProjectId] }),
      queryClient.invalidateQueries({ queryKey: ['assay-experiments', assayProjectId] }),
      queryClient.invalidateQueries({ queryKey: ['assay-studies', assayProjectId] }),
      queryClient.invalidateQueries({ queryKey: ['assay-guidance-results', assayProjectId] }),
      queryClient.invalidateQueries({ queryKey: ['assay-projects'] }),
    ])
  }
  const saveQuestion = useMutation({
    mutationFn: () => createScientificQuestion(assayProjectId, { question_key: questionKey, formal_question: formalQuestion, source: 'USER_SELECTED' }),
    onSuccess: async () => { setQuestionOpen(false); setQuestionKey(''); setFormalQuestion(''); await refresh() },
  })
  const saveContext = useMutation({
    mutationFn: () => updateAssayProject(assayProjectId, contextDraft),
    onSuccess: async () => { setContextOpen(false); await refresh() },
  })
  const resolve = useMutation({
    mutationFn: () => resolveRecommendation(decisionTarget!.id, decisionKind, { rationale }),
    onSuccess: async (result) => {
      const resolvedTarget = decisionTarget
      const resolvedKind = decisionKind
      setDecisionTarget(null)
      setRationale('')
      setNotice(result.action_launched === false ? 'Decision recorded. No analysis or experiment was launched automatically.' : null)
      await refresh()
      if (resolvedKind === 'accept' && resolvedTarget?.proposed_action.action_type === 'CREATE_EXPERIMENT') {
        navigate(`/assay-development/${assayProjectId}/experiments/new?recommendation=${encodeURIComponent(resolvedTarget.id)}`)
      }
      if (resolvedKind === 'accept' && resolvedTarget?.proposed_action.action_type === 'CREATE_ANALYSIS' && activeQuestion) {
        navigate(`/assay-development/${assayProjectId}/questions/${activeQuestion.id}/analysis`)
      }
      if (resolvedKind === 'accept' && resolvedTarget?.proposed_action.action_type === 'CREATE_STUDY') {
        navigate(`/assay-development/${assayProjectId}/studies/new?recommendation=${encodeURIComponent(resolvedTarget.id)}`)
      }
    },
  })
  const stageChange = useMutation({
    mutationFn: ({ recommendation, requestedStage, rationale: stageRationale }: { recommendation: Recommendation; requestedStage: AssayLifecycleStage; rationale: string }) => Promise.all([
      resolveRecommendation(recommendation.id, 'accept', { rationale: stageRationale }),
      recordStageDecision(assayProjectId, { requested_stage: requestedStage, decision: 'ACCEPT', rationale: stageRationale }),
    ]),
    onSuccess: async () => { setDecisionTarget(null); setRationale(''); setNotice('Stage decision recorded. No work was launched automatically.'); await refresh() },
  })

  if (assay.isPending || readiness.isPending) return <LoadingState label="Loading guided assay workspace…" />
  if (assay.isError) return <ErrorState error={assay.error} />
  if (readiness.isError) return <ErrorState error={readiness.error} />

  const openContext = () => {
    setContextDraft({
      proposed_purpose: assay.data.proposed_purpose || '',
      specimen_type: assay.data.specimen_type || '',
      biological_context: assay.data.biological_context || '',
      proposed_output: assay.data.proposed_output || '',
    })
    setContextOpen(true)
  }
  const beginRecommendation = (item: Recommendation) => {
    const action = String(item.proposed_action.action_type || '')
    if (action === 'EDIT_ASSAY_PROJECT') return openContext()
    if (action === 'OPEN_QUESTION_WIZARD') return setQuestionOpen(true)
    if (action === 'REVIEW_GUIDANCE_RESULT' && item.proposed_action.analysis_id) return navigate(`/analyses/${item.proposed_action.analysis_id}`)
    if (action === 'VIEW_STUDY_RESULT' && item.proposed_action.study_id) return navigate(`/studies/${item.proposed_action.study_id}`)
    if (['REVIEW_MODEL_CANDIDATE', 'LOCK_MODEL'].includes(action) && item.proposed_action.model_id) return navigate(`/models/${item.proposed_action.model_id}`)
    setDecisionKind('accept')
    setRationale('')
    setDecisionTarget(item)
  }

  return (
    <Stack spacing={4}>
      <Link component={RouterLink} to="/assay-development" underline="hover" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, width: 'fit-content' }}><ArrowBackRoundedIcon fontSize="small" /> Assay development</Link>
      <div>
        <Typography variant="overline" color="secondary.main" fontWeight={750}>Guided assay-development project</Typography>
        <Typography variant="h3" fontWeight={760}>{assay.data.name}</Typography>
        <Typography color="text.secondary" mt={1}>{assay.data.proposed_purpose || 'The proposed purpose still needs to be recorded.'}</Typography>
      </div>

      <Paper variant="outlined" sx={{ p: 2.5, overflowX: 'auto' }}>
        <Typography variant="overline" fontWeight={750}>Lifecycle stage</Typography>
        <Stack direction="row" spacing={1} mt={1} minWidth="max-content">
          {stages.map((stage) => <Chip key={stage} label={stage} color={stage === assay.data.current_stage ? 'secondary' : 'default'} variant={stage === assay.data.current_stage ? 'filled' : 'outlined'} />)}
        </Stack>
      </Paper>

      {notice && <Alert severity="info" onClose={() => setNotice(null)}>{notice}</Alert>}
      <Grid container spacing={2}>
        <Grid item xs={12} md={8}>
          <Paper variant="outlined" sx={{ p: 3, height: '100%' }}>
            <Typography variant="overline" color="secondary.main" fontWeight={750}>Current scientific question</Typography>
            <Typography variant="h5" fontWeight={720} mt={0.5}>{activeQuestion?.plain_language_question || 'No active question selected'}</Typography>
            <Typography color="text.secondary" mt={1}>{activeQuestion?.formal_question || 'Select what you are trying to learn before choosing an analysis or experiment.'}</Typography>
            <Button variant="contained" color="secondary" sx={{ mt: 2 }} onClick={() => setQuestionOpen(true)}>{activeQuestion ? 'Change question' : 'Select a question'}</Button>
          </Paper>
        </Grid>
        <Grid item xs={12} md={4}>
          <Paper variant="outlined" sx={{ p: 3, height: '100%' }}>
            <Typography variant="overline" fontWeight={750}>Overall readiness</Typography>
            <Chip label={readiness.data.status.replaceAll('_', ' ')} color={readiness.data.status === 'BLOCKED' ? 'error' : readiness.data.status === 'READY_FOR_RECOMMENDED_ACTION' ? 'success' : 'warning'} sx={{ mt: 1, display: 'flex', width: 'fit-content' }} />
            <Typography variant="body2" color="text.secondary" mt={2}>Evaluated with deterministic, stage-aware rules. No hidden score is used.</Typography>
          </Paper>
        </Grid>
      </Grid>

      <Grid container spacing={2}>
        <Grid item xs={12} md={6}><EvidenceItems title="What is known" items={readiness.data.ready_items} kind="ready" /></Grid>
        <Grid item xs={12} md={6}><EvidenceItems title="What remains unresolved" items={readiness.data.missing_items} kind="missing" /></Grid>
        <Grid item xs={12} md={6}><EvidenceItems title="Blocking issues" items={readiness.data.blockers} kind="blocker" /></Grid>
        <Grid item xs={12} md={6}><EvidenceItems title="Warnings" items={readiness.data.warnings} kind="warning" /></Grid>
      </Grid>

      <div>
        <Typography variant="overline" color="secondary.main" fontWeight={750}>Scientist decision required</Typography>
        <Typography variant="h4" fontWeight={740}>Recommended next actions</Typography>
      </div>
      {recommendations.isError && <ErrorState error={recommendations.error} />}
      {recommendations.data?.length === 0 && <Typography color="text.secondary">No open recommendations.</Typography>}
      <Grid container spacing={2}>
        {recommendations.data?.map((item) => <Grid item xs={12} key={item.id}>
          <Card variant="outlined" sx={{ borderLeft: 6, borderLeftColor: `${requirementColor[item.requirement_level]}.main` }}>
            <CardContent>
              <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={1}>
                <div><Chip size="small" label={item.requirement_level.replaceAll('_', ' ')} color={requirementColor[item.requirement_level]} /><Typography variant="h5" fontWeight={720} mt={1}>{item.title}</Typography></div>
                <Chip label={`Rule ${item.rule_id}`} variant="outlined" size="small" />
              </Stack>
              <Typography mt={1}>{item.summary}</Typography>
              <Grid container spacing={2} mt={0.5}>
                <Grid item xs={12} md={4}><Typography variant="overline" fontWeight={750}>Why</Typography><Typography variant="body2">{item.why}</Typography></Grid>
                <Grid item xs={12} md={4}><Typography variant="overline" fontWeight={750}>Resolves</Typography><Typography variant="body2">{item.what_it_resolves}</Typography></Grid>
                <Grid item xs={12} md={4}><Typography variant="overline" fontWeight={750}>Limitations</Typography><Typography variant="body2">{item.limitations.join(' ') || 'None declared.'}</Typography></Grid>
              </Grid>
              <Typography variant="caption" color="text.secondary" display="block" mt={2}>Evidence: {JSON.stringify(item.evidence_refs)}</Typography>
            </CardContent>
            <CardActions>
              <Button variant="contained" color="secondary" onClick={() => beginRecommendation(item)}>{item.proposed_action.action_type === 'REVIEW_GUIDANCE_RESULT' ? 'Review source results' : 'Create recommended action'}</Button>
              <Button onClick={() => { setDecisionKind('reject'); setRationale(''); setDecisionTarget(item) }}>Reject or defer</Button>
            </CardActions>
          </Card>
        </Grid>)}
      </Grid>

      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography variant="h5" fontWeight={720}>Five-question stage card</Typography>
        <Grid container spacing={2} mt={0.5}>
          {[
            ['Question', activeQuestion?.plain_language_question || 'Select the decision being addressed.'],
            ['Requirements', activeQuestion ? 'Review the cataloged inputs, metadata, controls, and design checks.' : 'A scientific question is required first.'],
            ['Action', recommendations.data?.[0]?.title || 'Resolve missing information before choosing an action.'],
            ['Evidence', `${readiness.data.ready_items.length} known item(s); ${readiness.data.blockers.length} blocker(s).`],
            ['Next decision', 'Accept, reject, modify, or defer the recommendation with rationale.'],
          ].map(([title, body]) => <Grid item xs={12} md key={title}><Typography variant="overline" color="secondary.main" fontWeight={750}>{title}</Typography><Typography variant="body2">{body}</Typography></Grid>)}
        </Grid>
      </Paper>

      <div>
        <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={1}>
          <div><Typography variant="overline" color="secondary.main" fontWeight={750}>Controlled experiment revisions</Typography><Typography variant="h4" fontWeight={740}>Development Experiments</Typography></div>
          {['usable_rna_feasibility', 'input_degradation_stability', 'paired_condition_performance', 'multifactor_optimization'].includes(activeQuestion?.question_key || '') && <Button component={RouterLink} to={`/assay-development/${assayProjectId}/experiments/new`} variant="outlined" color="secondary">Create experiment draft</Button>}
        </Stack>
        {experiments.isError && <ErrorState error={experiments.error} />}
        {experiments.data?.length === 0 && <Typography color="text.secondary" mt={1}>No experiment revisions yet. Accept a routed recommendation or create a controlled draft.</Typography>}
        <Grid container spacing={2} mt={0.5}>{experiments.data?.map((experiment) => <Grid item xs={12} md={6} key={experiment.id}><Card component={RouterLink} to={`/experiments/${experiment.id}`} variant="outlined" sx={{ height: '100%', display: 'block', textDecoration: 'none', color: 'inherit', '&:hover': { borderColor: 'secondary.main' } }}><CardContent><Stack direction="row" justifyContent="space-between" gap={1}><Typography variant="h6" fontWeight={700}>{experiment.name}</Typography><Chip size="small" label={experiment.status.replaceAll('_', ' ')} color={experiment.status === 'SUCCEEDED' || experiment.status === 'DESIGN_VALID' ? 'success' : experiment.status === 'DESIGN_INVALID' || experiment.status === 'FAILED' ? 'error' : 'default'} /></Stack><Typography variant="body2" color="text.secondary" mt={1}>Revision {experiment.current_revision} · {experiment.assignments.length} measurement assignments</Typography></CardContent></Card></Grid>)}</Grid>
      </div>

      <div>
        <Typography variant="overline" color="secondary.main" fontWeight={750}>Question-aware analysis evidence</Typography>
        <Typography variant="h4" fontWeight={740}>Guided analysis results</Typography>
        {guidanceResults.isError && <ErrorState error={guidanceResults.error} />}
        {guidanceResults.data?.length === 0 && <Typography color="text.secondary" mt={1}>No guided existing-analysis results yet.</Typography>}
        <Grid container spacing={2} mt={0.5}>{guidanceResults.data?.map((result) => <Grid item xs={12} md={6} key={result.id}><Card variant="outlined" sx={{ height: '100%' }}><CardContent><Chip size="small" label={result.payload_json.analysis_type.replaceAll('_', ' ')} color="secondary" /><Typography variant="h6" fontWeight={700} mt={1.5}>{result.payload_json.question_answered}</Typography><Typography mt={1}>{result.payload_json.important_findings.join(' ')}</Typography><Alert severity="warning" sx={{ mt: 2 }}>{result.payload_json.unresolved_risks.join(' ')}</Alert><Typography variant="body2" mt={2}><strong>Next:</strong> {result.payload_json.recommended_next_actions.join(' ')}</Typography><Typography variant="caption" color="text.secondary" display="block" mt={1}>Evidence references: {result.payload_json.evidence_refs.length} · Guidance SHA-256 {result.artifact_sha256}</Typography></CardContent><CardActions><Button component={RouterLink} to={`/analyses/${result.analysis_id}`} variant="outlined">Open source results</Button></CardActions></Card></Grid>)}</Grid>
      </div>

      <div>
        <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={1}>
          <div><Typography variant="overline" color="secondary.main" fontWeight={750}>Locked endpoint evidence</Typography><Typography variant="h4" fontWeight={740}>Analytical Validation Studies</Typography></div>
          {['precision_reproducibility', 'input_degradation_limit_validation', 'paired_bridging_equivalence', 'robustness_interference_validation'].includes(activeQuestion?.question_key || '') && <Button component={RouterLink} to={`/assay-development/${assayProjectId}/studies/new`} variant="outlined" color="secondary">Create validation study</Button>}
        </Stack>
        {studies.isError && <ErrorState error={studies.error} />}
        {studies.data?.length === 0 && <Typography color="text.secondary" mt={1}>No post-lock validation studies yet. A locked model and explicit repeated-measure design are required.</Typography>}
        <Grid container spacing={2} mt={0.5}>{studies.data?.map((study) => <Grid item xs={12} md={6} key={study.id}><Card component={RouterLink} to={`/studies/${study.id}`} variant="outlined" sx={{ height: '100%', display: 'block', textDecoration: 'none', color: 'inherit', '&:hover': { borderColor: 'secondary.main' } }}><CardContent><Stack direction="row" justifyContent="space-between" gap={1}><Typography variant="h6" fontWeight={700}>{study.name}</Typography><Chip size="small" label={study.status.replaceAll('_', ' ')} color={study.status === 'SUCCEEDED' || study.status === 'DESIGN_VALID' ? 'success' : study.status === 'DESIGN_INVALID' || study.status === 'FAILED' ? 'error' : ['QUEUED', 'RUNNING'].includes(study.status) ? 'warning' : 'default'} /></Stack><Typography variant="body2" color="text.secondary" mt={1}>Revision {study.current_revision} · {study.assignments_json.length} measurements · locked model {study.model_id}</Typography></CardContent></Card></Grid>)}</Grid>
      </div>

      <div>
        <Typography variant="h5" fontWeight={720}>Recent decisions</Typography>
        {decisions.data?.length === 0 && <Typography color="text.secondary" mt={1}>No material decisions recorded yet.</Typography>}
        <Stack spacing={1.5} mt={1.5}>{decisions.data?.slice(0, 5).map((item) => <Paper variant="outlined" sx={{ p: 2 }} key={item.id}><Stack direction="row" spacing={1} alignItems="center"><Chip label={item.selected_option} size="small" /><Typography fontWeight={650}>{item.decision}</Typography></Stack><Typography color="text.secondary" variant="body2" mt={1}>{item.rationale}</Typography></Paper>)}</Stack>
      </div>

      <Dialog open={questionOpen} onClose={() => setQuestionOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>What are you trying to learn?</DialogTitle>
        <DialogContent><Stack spacing={2} mt={1}>
          <Alert icon={<HelpOutlineRoundedIcon />} severity="info">Choose a supported scientific question. TranscriptForge will route it to a constrained design; it will not choose your endpoint or launch work.</Alert>
          <TextField select label="Scientific question" value={questionKey} onChange={(event) => { setQuestionKey(event.target.value); const route = catalog.data?.questions.find((item) => item.key === event.target.value); setFormalQuestion(route?.question || '') }}>
            {catalog.data?.questions.map((item) => <MenuItem value={item.key} key={item.key}>{item.stage}: {item.question}</MenuItem>)}
          </TextField>
          {selectedRoute && <Paper variant="outlined" sx={{ p: 2 }}><Typography fontWeight={700}>What this means</Typography><Typography variant="body2" mt={0.5}>Route: {selectedRoute.experiment_type || selectedRoute.analysis_type || selectedRoute.study_type || 'model lock review'}</Typography><Typography variant="body2" mt={1}><strong>Required metadata:</strong> {selectedRoute.required_metadata.join(', ') || 'No additional cataloged metadata.'}</Typography><Typography variant="body2" mt={1}><strong>Design checks:</strong> {selectedRoute.design_checks.join(', ')}</Typography><Typography variant="body2" mt={1}><strong>Recommended endpoints:</strong> {selectedRoute.recommended_endpoints.join(', ')}</Typography></Paper>}
          <TextField label="Formal question and decision to inform" multiline minRows={3} value={formalQuestion} onChange={(event) => setFormalQuestion(event.target.value)} helperText="State the comparison, endpoint, and decision in your own words. This remains visible on final review." />
          {saveQuestion.isError && <ErrorState error={saveQuestion.error} />}
        </Stack></DialogContent>
        <DialogActions><Button onClick={() => setQuestionOpen(false)}>Cancel</Button><Button variant="contained" color="secondary" disabled={!questionKey || !formalQuestion.trim() || saveQuestion.isPending} onClick={() => saveQuestion.mutate()}>Save scientific question</Button></DialogActions>
      </Dialog>

      <Dialog open={contextOpen} onClose={() => setContextOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Complete the proposed assay context</DialogTitle>
        <DialogContent><Stack spacing={2} mt={1}>
          <TextField label="Proposed purpose" multiline minRows={2} value={contextDraft.proposed_purpose} onChange={(event) => setContextDraft((value) => ({ ...value, proposed_purpose: event.target.value }))} />
          <TextField label="Specimen type" value={contextDraft.specimen_type} onChange={(event) => setContextDraft((value) => ({ ...value, specimen_type: event.target.value }))} />
          <TextField label="Biological context" multiline minRows={2} value={contextDraft.biological_context} onChange={(event) => setContextDraft((value) => ({ ...value, biological_context: event.target.value }))} />
          <TextField label="Proposed output" value={contextDraft.proposed_output} onChange={(event) => setContextDraft((value) => ({ ...value, proposed_output: event.target.value }))} />
          {saveContext.isError && <ErrorState error={saveContext.error} />}
        </Stack></DialogContent>
        <DialogActions><Button onClick={() => setContextOpen(false)}>Cancel</Button><Button variant="contained" color="secondary" disabled={saveContext.isPending} onClick={() => saveContext.mutate()}>Save and recompute readiness</Button></DialogActions>
      </Dialog>

      <Dialog open={decisionTarget !== null} onClose={() => setDecisionTarget(null)} fullWidth maxWidth="sm">
        <DialogTitle>{decisionKind === 'accept' ? 'Accept recommended action' : 'Reject or defer recommendation'}</DialogTitle>
        <DialogContent><Stack spacing={2} mt={1}>
          <Typography>{decisionTarget?.title}</Typography>
          <Alert severity="warning">A rationale is required. Acceptance creates a controlled draft or stage decision; it never launches automatically.</Alert>
          <TextField label="Scientist rationale" multiline minRows={3} required value={rationale} onChange={(event) => setRationale(event.target.value)} />
          {(resolve.isError || stageChange.isError) && <ErrorState error={resolve.error || stageChange.error} />}
        </Stack></DialogContent>
        <DialogActions><Button onClick={() => setDecisionTarget(null)}>Cancel</Button><Button variant="contained" color={decisionKind === 'accept' ? 'secondary' : 'error'} disabled={!rationale.trim() || resolve.isPending || stageChange.isPending} onClick={() => {
          const requestedStage = decisionTarget?.proposed_action.requested_stage as AssayLifecycleStage | undefined
          if (decisionTarget && decisionKind === 'accept' && requestedStage) stageChange.mutate({ recommendation: decisionTarget, requestedStage, rationale })
          else resolve.mutate()
        }}>{decisionKind === 'accept' ? 'Accept and create draft' : 'Record rejection'}</Button></DialogActions>
      </Dialog>
    </Stack>
  )
}
