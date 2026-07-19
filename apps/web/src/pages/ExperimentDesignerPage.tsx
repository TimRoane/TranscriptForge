import ArrowBackRoundedIcon from '@mui/icons-material/ArrowBackRounded'
import {
  Alert,
  Button,
  Grid,
  Link,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import {
  type ExperimentAssignment,
  createDevelopmentExperiment,
  fetchAssayProject,
  fetchExperimentDesignOptions,
  fetchExperimentInputOptions,
  fetchScientificQuestions,
} from '../api/client'
import { ErrorState, LoadingState } from '../components/ApiState'
import { ExperimentAssignmentTable } from '../components/ExperimentAssignmentTable'

function numeric(value: string | undefined): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

export function ExperimentDesignerPage() {
  const { assayProjectId = '' } = useParams()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const assay = useQuery({ queryKey: ['assay-project', assayProjectId], queryFn: ({ signal }) => fetchAssayProject(assayProjectId, signal), enabled: !!assayProjectId })
  const questions = useQuery({ queryKey: ['assay-questions', assayProjectId], queryFn: ({ signal }) => fetchScientificQuestions(assayProjectId, signal), enabled: !!assayProjectId })
  const inputs = useQuery({ queryKey: ['experiment-input-options', assayProjectId], queryFn: ({ signal }) => fetchExperimentInputOptions(assayProjectId, signal), enabled: !!assayProjectId })
  const [preparedId, setPreparedId] = useState('')
  const designOptions = useQuery({ queryKey: ['experiment-design-options', preparedId], queryFn: ({ signal }) => fetchExperimentDesignOptions(preparedId, signal), enabled: !!preparedId })
  const [name, setName] = useState('RNA input and degradation exploration')
  const [objective, setObjective] = useState('Explore paired expression stability across declared RNA input and degradation conditions.')
  const [mode, setMode] = useState<'PLAN_FIRST' | 'ANALYZE_EXISTING'>('ANALYZE_EXISTING')
  const [assayName, setAssayName] = useState('log_expression')
  const [referenceLevel, setReferenceLevel] = useState(100)
  const [referenceCondition, setReferenceCondition] = useState('reference')
  const [comparatorCondition, setComparatorCondition] = useState('comparator')
  const [declaredQuestion, setDeclaredQuestion] = useState('Does paired expression-profile stability remain interpretable across the tested input levels?')
  const [referenceRationale, setReferenceRationale] = useState('The highest declared input condition is the development reference.')
  const [endpointRationale, setEndpointRationale] = useState('Paired profile correlation and detected genes directly characterize expression stability before model development.')
  const [conditionRationale, setConditionRationale] = useState('The reference condition is the current development process and the comparator is the candidate process.')
  const [assignments, setAssignments] = useState<ExperimentAssignment[]>([])
  const activeQuestion = questions.data?.find((item) => item.id === assay.data?.active_question_id)
  const technicalFeasibility = activeQuestion?.question_key === 'usable_rna_feasibility'
  const pairedCondition = activeQuestion?.question_key === 'paired_condition_performance'
  const multifactor = activeQuestion?.question_key === 'multifactor_optimization'

  useEffect(() => {
    if (!technicalFeasibility) return
    setName('Usable RNA technical feasibility')
    setObjective('Summarize technical usability across explicitly tested specimens and processing conditions.')
    setDeclaredQuestion('Do tested samples generate technically usable expression measurements that merit further assay development?')
    setEndpointRationale('Technical success, detected genes, RNA quantity and quality, and explicit failure patterns provide complementary feasibility evidence.')
    setConditionRationale('Specimen groups and technical factors are reviewed descriptively; no clinical specimen requirement is inferred.')
  }, [technicalFeasibility])

  useEffect(() => {
    if (!pairedCondition) return
    setName('Paired extraction or library-condition comparison')
    setObjective('Compare paired expression performance across two declared processing conditions using complementary endpoints.')
    setDeclaredQuestion('Do paired bias, profile concordance, failures, discordance, and quality interactions jointly support either condition?')
    setEndpointRationale('Paired bias, uncertainty, profile correlation, failures, and per-sample discordance provide complementary evidence; no condition is ranked from one endpoint.')
  }, [pairedCondition])

  useEffect(() => {
    if (!multifactor) return
    setName('Constrained extraction method and input optimization')
    setObjective('Estimate prespecified extraction-method, input-level, and interaction effects while blocking repeated biological samples and run.')
    setDeclaredQuestion('Which tested method and input combinations merit prospective confirmation?')
    setEndpointRationale('Fixed effects, supported interactions, cell means, and descriptive variance components provide complementary pre-lock evidence.')
    setConditionRationale('Extraction method and input are controllable primary factors; their interaction is prespecified and the model is capped at two primary factors.')
  }, [multifactor])

  useEffect(() => {
    if (!preparedId && inputs.data?.length) setPreparedId(inputs.data[0].prepared_dataset_id)
  }, [inputs.data, preparedId])

  useEffect(() => {
    if (!designOptions.data) return
    const mapped = designOptions.data.metadata_rows.map((row, index) => ({
      measurement_id: row.sample_id,
      biological_sample_id: row.biological_sample_id || '',
      prepared_dataset_id: designOptions.data.prepared_dataset_id,
      include: true,
      exclusion_reason: null,
      replicate_id: row.replicate_id || null,
      pair_id: row.biological_sample_id || null,
      input_ng: numeric(row.input_ng) || null,
      dv200: row.dv200 === undefined || row.dv200 === '' ? null : numeric(row.dv200),
      sequencing_run: row.sequencing_run || null,
      condition: row.condition || row.method || null,
      run: row.run || row.sequencing_run || null,
      quality_metric: row.quality_metric === undefined || row.quality_metric === '' ? (row.dv200 ? numeric(row.dv200) : null) : numeric(row.quality_metric),
      operator: row.operator || null,
      reagent_lot: row.reagent_lot || null,
      instrument: row.instrument || null,
      processing_order: numeric(row.processing_order) || index + 1,
      extraction_method: row.extraction_method || row.method || row.condition || null,
      library_method: row.library_method || null,
      sequencing_depth: numeric(row.sequencing_depth) || null,
      specimen_group: row.specimen_group || row.specimen_type || null,
      technical_failure: ['true', '1', 'yes'].includes((row.technical_failure || '').toLowerCase()),
    }))
    setAssignments(mapped)
    if (designOptions.data.assays.includes('log_expression')) setAssayName('log_expression')
    else if (designOptions.data.assays.length) setAssayName(designOptions.data.assays[0])
    const levels = mapped.map((item) => item.input_ng || 0).filter((value) => value > 0)
    if (levels.length) setReferenceLevel(Math.max(...levels))
    const conditions = [...new Set(mapped.map((item) => item.condition).filter((value): value is string => !!value))]
    if (conditions.length) setReferenceCondition(conditions[0])
    if (conditions.length > 1) setComparatorCondition(conditions[1])
  }, [designOptions.data])

  const missingRequired = useMemo(() => assignments.filter((item) => item.include && (
    !item.biological_sample_id.trim()
    || (technicalFeasibility
      ? !(item.run || item.sequencing_run)?.trim()
      : pairedCondition
      ? !item.condition?.trim() || !item.run?.trim()
      : multifactor
        ? !item.extraction_method?.trim() || !item.input_ng || !item.run?.trim()
      : !item.input_ng || item.input_ng <= 0 || item.dv200 === null || !item.sequencing_run?.trim())
  )).length, [assignments, technicalFeasibility, pairedCondition, multifactor])
  const create = useMutation({
    mutationFn: () => createDevelopmentExperiment({
      assay_project_id: assayProjectId,
      question_id: activeQuestion!.id,
      prepared_dataset_id: preparedId,
      name,
      objective,
      experiment_type: technicalFeasibility ? 'TECHNICAL_FEASIBILITY' : pairedCondition ? 'PAIRED_CONDITION_COMPARISON' : multifactor ? 'MULTIFACTOR_OPTIMIZATION' : 'INPUT_DEGRADATION_EXPLORATION',
      mode,
      ...(technicalFeasibility ? {
        condition_contrast_rationale: conditionRationale,
      } : pairedCondition ? {
        reference_condition: referenceCondition,
        comparator_condition: comparatorCondition,
        condition_contrast_rationale: conditionRationale,
      } : multifactor ? {
        condition_contrast_rationale: conditionRationale,
        factor_names: ['extraction_method', 'input_ng'],
        interactions: ['extraction_method:input_ng'],
      } : {
        reference_level: referenceLevel,
        reference_level_rationale: referenceRationale,
      }),
      assay: assayName,
      primary_endpoints: technicalFeasibility ? ['technical_success_rate', 'detected_genes'] : pairedCondition ? ['paired_mean_expression_difference', 'expression_profile_correlation'] : multifactor ? ['mean_expression', 'fixed_effect_estimates'] : ['expression_profile_correlation_to_reference', 'detected_genes'],
      secondary_endpoints: technicalFeasibility ? ['input_ng', 'dv200', 'failure_association_review'] : pairedCondition ? ['failure_rate', 'per_sample_discordance', 'condition_by_quality_interaction'] : multifactor ? ['detected_genes', 'variance_decomposition'] : ['mean_expression'],
      declared_questions: [declaredQuestion],
      endpoint_rationale: endpointRationale,
      assignments,
    }),
    onSuccess: (experiment) => navigate(`/experiments/${experiment.id}`),
  })

  if (assay.isPending || questions.isPending || inputs.isPending) return <LoadingState label="Opening Experiment Designer…" />
  if (assay.isError || questions.isError || inputs.isError) return <ErrorState error={assay.error || questions.error || inputs.error} />
  const supportedQuestion = ['usable_rna_feasibility', 'input_degradation_stability', 'paired_condition_performance', 'multifactor_optimization'].includes(activeQuestion?.question_key || '')

  return <Stack spacing={4}>
    <Link component={RouterLink} to={`/assay-development/${assayProjectId}`} underline="hover" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, width: 'fit-content' }}><ArrowBackRoundedIcon fontSize="small" /> {assay.data.name}</Link>
    <div><Typography variant="overline" color="secondary.main" fontWeight={750}>Experiment Designer · controlled draft</Typography><Typography variant="h3" fontWeight={760}>{technicalFeasibility ? 'Usable RNA technical feasibility' : pairedCondition ? 'Paired condition comparison' : multifactor ? 'Constrained multifactor optimization' : 'Input and degradation exploration'}</Typography><Typography color="text.secondary" mt={1}>Map explicit measurement metadata, inspect confounding checks, then lock an immutable revision. Creating this draft does not run computation.</Typography></div>
    {searchParams.get('recommendation') && <Alert severity="success">Recommendation accepted. The follow-up is now a visible draft; no experiment has been launched.</Alert>}
    {!supportedQuestion && <Alert severity="error">The active scientific question does not support an implemented experiment template. Return to the guided workspace and select input/degradation stability or paired-condition performance.</Alert>}
    {inputs.data.length === 0 && <Alert severity="warning">No prepared Expression Bundle is available in the linked project. Prepare a dataset before creating this experiment.</Alert>}
    <Paper variant="outlined" sx={{ p: 3 }}><Grid container spacing={2}>
      <Grid item xs={12} md={8}><TextField fullWidth label="Experiment name" value={name} onChange={(event) => setName(event.target.value)} /></Grid>
      <Grid item xs={12} md={4}><TextField select fullWidth label="Mode" value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}><MenuItem value="PLAN_FIRST">Plan first</MenuItem><MenuItem value="ANALYZE_EXISTING">Analyze existing measurements</MenuItem></TextField></Grid>
      <Grid item xs={12}><TextField fullWidth multiline minRows={2} label="Objective" value={objective} onChange={(event) => setObjective(event.target.value)} /></Grid>
      <Grid item xs={12} md={8}><TextField select fullWidth label="Prepared Expression Bundle" value={preparedId} onChange={(event) => setPreparedId(event.target.value)}>{inputs.data.map((item) => <MenuItem key={item.prepared_dataset_id} value={item.prepared_dataset_id}>{item.dataset_name} · v{item.prepared_version} · {item.sample_count} measurements · {item.qc_status}</MenuItem>)}</TextField></Grid>
      <Grid item xs={6} md={2}><TextField select fullWidth label="Assay" value={assayName} onChange={(event) => setAssayName(event.target.value)}>{(designOptions.data?.assays || ['log_expression']).map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}</TextField></Grid>
      {technicalFeasibility ? <Grid item xs={6} md={2}><TextField fullWidth disabled label="Evidence mode" value="Exploratory" /></Grid> : pairedCondition ? <>
        <Grid item xs={6} md={2}><TextField fullWidth label="Reference condition" value={referenceCondition} onChange={(event) => setReferenceCondition(event.target.value)} /></Grid>
        <Grid item xs={6} md={2}><TextField fullWidth label="Comparator condition" value={comparatorCondition} onChange={(event) => setComparatorCondition(event.target.value)} /></Grid>
      </> : multifactor ? <Grid item xs={6} md={2}><TextField fullWidth disabled label="Frozen factors" value="method × input" /></Grid> : <Grid item xs={6} md={2}><TextField fullWidth type="number" label="Reference input (ng)" value={referenceLevel} onChange={(event) => setReferenceLevel(Number(event.target.value))} /></Grid>}
      <Grid item xs={12}><TextField fullWidth multiline minRows={2} label="Declared learning question" value={declaredQuestion} onChange={(event) => setDeclaredQuestion(event.target.value)} /></Grid>
      <Grid item xs={12} md={6}><TextField fullWidth multiline minRows={2} label={technicalFeasibility ? 'Feasibility scope rationale' : pairedCondition ? 'Condition contrast rationale' : multifactor ? 'Factor and interaction rationale' : 'Reference-level rationale'} value={technicalFeasibility || pairedCondition || multifactor ? conditionRationale : referenceRationale} onChange={(event) => technicalFeasibility || pairedCondition || multifactor ? setConditionRationale(event.target.value) : setReferenceRationale(event.target.value)} /></Grid>
      <Grid item xs={12} md={6}><TextField fullWidth multiline minRows={2} label="Endpoint rationale" value={endpointRationale} onChange={(event) => setEndpointRationale(event.target.value)} /></Grid>
    </Grid></Paper>
    <div><Typography variant="h4" fontWeight={740}>Measurement assignments</Typography><Typography color="text.secondary" mt={0.5}>Values are copied only from explicit metadata columns. Blank fields require scientist mapping; values are never inferred from filenames.</Typography></div>
    {designOptions.isPending && <LoadingState label="Reading immutable bundle metadata…" />}
    {designOptions.isError && <ErrorState error={designOptions.error} />}
    <ExperimentAssignmentTable assignments={assignments} editable template={technicalFeasibility ? 'technical_feasibility' : pairedCondition ? 'paired_condition' : multifactor ? 'multifactor' : 'input_degradation'} onChange={setAssignments} />
    {missingRequired > 0 && <Alert severity="warning">{missingRequired} included measurement(s) still need biological sample and {technicalFeasibility ? 'run' : pairedCondition ? 'condition/run' : multifactor ? 'extraction-method/input/run' : 'input/DV200/sequencing-run'} metadata.</Alert>}
    {create.isError && <ErrorState error={create.error} />}
    <Stack direction="row" spacing={2}><Button variant="contained" color="secondary" size="large" disabled={!supportedQuestion || !assignments.length || missingRequired > 0 || !name.trim() || !objective.trim() || create.isPending} onClick={() => create.mutate()}>Create draft and validate design</Button><Button component={RouterLink} to={`/assay-development/${assayProjectId}`}>Cancel</Button></Stack>
  </Stack>
}
