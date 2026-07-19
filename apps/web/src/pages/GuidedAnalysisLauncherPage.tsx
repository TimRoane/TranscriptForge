import ArrowBackRoundedIcon from '@mui/icons-material/ArrowBackRounded'
import ArrowForwardRoundedIcon from '@mui/icons-material/ArrowForwardRounded'
import { Alert, Button, Card, CardActions, CardContent, Chip, Grid, Link, Stack, Typography } from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { Link as RouterLink, useParams } from 'react-router-dom'

import { fetchExperimentInputOptions, fetchQuestionCatalog, fetchScientificQuestions } from '../api/client'
import { ErrorState, LoadingState } from '../components/ApiState'

export function GuidedAnalysisLauncherPage() {
  const { assayProjectId = '', questionId = '' } = useParams()
  const inputs = useQuery({ queryKey: ['guided-analysis-inputs', assayProjectId], queryFn: ({ signal }) => fetchExperimentInputOptions(assayProjectId, signal), enabled: !!assayProjectId })
  const questions = useQuery({ queryKey: ['assay-questions', assayProjectId], queryFn: ({ signal }) => fetchScientificQuestions(assayProjectId, signal), enabled: !!assayProjectId })
  const catalog = useQuery({ queryKey: ['scientific-question-catalog'], queryFn: ({ signal }) => fetchQuestionCatalog(signal) })
  if (inputs.isPending || questions.isPending || catalog.isPending) return <LoadingState label="Routing the guided analysis…" />
  if (inputs.isError || questions.isError || catalog.isError) return <ErrorState error={inputs.error || questions.error || catalog.error} />
  const question = questions.data.find((item) => item.id === questionId)
  const route = catalog.data.questions.find((item) => item.key === question?.question_key)
  if (!question || !route?.analysis_type) return <ErrorState error={new Error('This scientific question does not route to an existing analysis workflow.')} />

  return <Stack spacing={4}>
    <Link component={RouterLink} to={`/assay-development/${assayProjectId}`} underline="hover" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, width: 'fit-content' }}><ArrowBackRoundedIcon fontSize="small" /> Guided assay workspace</Link>
    <div><Typography variant="overline" color="secondary.main" fontWeight={750}>Guided existing analysis</Typography><Typography variant="h3" fontWeight={760}>{question.plain_language_question}</Typography><Typography color="text.secondary" mt={1}>{question.formal_question}</Typography></div>
    <Alert severity="info">TranscriptForge is routing this question to the existing <strong>{route.analysis_type.replaceAll('_', ' ')}</strong> workflow. Select the immutable Expression Bundle, then review its complete scientific design before saving or running.</Alert>
    <div><Typography variant="h4" fontWeight={740}>Choose the evidence input</Typography><Typography color="text.secondary" mt={0.5}>No filenames are inferred and no analysis launches from this selection.</Typography></div>
    <Grid container spacing={2}>{inputs.data.map((item) => {
      const query = new URLSearchParams({ assayProjectId, scientificQuestionId: question.id, guidedAnalysisType: route.analysis_type! })
      return <Grid item xs={12} md={6} key={item.prepared_dataset_id}><Card variant="outlined" sx={{ height: '100%' }}><CardContent><Typography variant="h6" fontWeight={700}>{item.dataset_name}</Typography><Stack direction="row" gap={1} flexWrap="wrap" mt={1.5}><Chip size="small" label={`Bundle v${item.prepared_version}`} /><Chip size="small" label={`${item.sample_count} samples`} /><Chip size="small" label={`${item.feature_count.toLocaleString()} features`} /><Chip size="small" color={item.qc_status === 'PASS' ? 'success' : 'warning'} label={`QC ${item.qc_status}`} /></Stack><Typography variant="body2" color="text.secondary" mt={1.5}>Assays: {item.assays.join(', ')}</Typography></CardContent><CardActions><Button component={RouterLink} to={`/prepared-datasets/${item.prepared_dataset_id}?${query.toString()}`} endIcon={<ArrowForwardRoundedIcon />} variant="contained" color="secondary">Configure this analysis</Button></CardActions></Card></Grid>
    })}</Grid>
  </Stack>
}
