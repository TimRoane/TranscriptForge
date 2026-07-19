import ArrowBackRoundedIcon from '@mui/icons-material/ArrowBackRounded'
import {
  Alert,
  Button,
  Checkbox,
  FormControlLabel,
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
  type StudyAssignment,
  createAnalyticalStudy,
  fetchAssayProject,
  fetchExperimentDesignOptions,
  fetchScientificQuestions,
  fetchStudyInputOptions,
} from '../api/client'
import { ErrorState, LoadingState } from '../components/ApiState'
import { StudyAssignmentTable } from '../components/StudyAssignmentTable'

const optionalFactors = ['reagent_lot', 'instrument', 'day', 'site'] as const

export function StudyDesignerPage() {
  const { assayProjectId = '' } = useParams()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [modelId, setModelId] = useState('')
  const [preparedId, setPreparedId] = useState('')
  const [name, setName] = useState('Classifier precision and reproducibility')
  const [objective, setObjective] = useState('Quantify repeatability and reproducibility of the locked classifier score and categorical call under the tested conditions.')
  const [assignments, setAssignments] = useState<StudyAssignment[]>([])
  const [factors, setFactors] = useState<string[]>(['operator', 'run'])
  const [iccThreshold, setIccThreshold] = useState(0.9)
  const [agreementThreshold, setAgreementThreshold] = useState(0.95)
  const [iccRationale, setIccRationale] = useState('Prespecified research-use threshold for the locked score endpoint.')
  const [agreementRationale, setAgreementRationale] = useState('Prespecified research-use threshold for categorical call consistency.')
  const [proximityBand, setProximityBand] = useState(0.1)
  const [referenceLevel, setReferenceLevel] = useState(100)
  const [scoreDifferenceThreshold, setScoreDifferenceThreshold] = useState(0.1)
  const [failureRateThreshold, setFailureRateThreshold] = useState(0.1)
  const [levelRationale, setLevelRationale] = useState('The highest tested input is the locked-endpoint reference and lower consecutive levels are evaluated in descending order.')
  const [referenceCondition, setReferenceCondition] = useState('reference')
  const [comparatorCondition, setComparatorCondition] = useState('comparator')
  const [equivalenceMargin, setEquivalenceMargin] = useState(0.05)
  const [conditionRationale, setConditionRationale] = useState('The reference is the current locked assay pipeline and the comparator is the candidate bridge condition.')

  const assay = useQuery({ queryKey: ['assay-project', assayProjectId], queryFn: ({ signal }) => fetchAssayProject(assayProjectId, signal), enabled: !!assayProjectId })
  const questions = useQuery({ queryKey: ['assay-questions', assayProjectId], queryFn: ({ signal }) => fetchScientificQuestions(assayProjectId, signal), enabled: !!assayProjectId })
  const options = useQuery({ queryKey: ['study-input-options', assayProjectId], queryFn: ({ signal }) => fetchStudyInputOptions(assayProjectId, signal), enabled: !!assayProjectId })
  const design = useQuery({ queryKey: ['study-design-options', preparedId], queryFn: ({ signal }) => fetchExperimentDesignOptions(preparedId, signal), enabled: !!preparedId })
  const question = questions.data?.find((item) => item.id === assay.data?.active_question_id && item.status === 'OPEN')
  const inputLimit = question?.question_key === 'input_degradation_limit_validation'
  const pairedBridge = question?.question_key === 'paired_bridging_equivalence'
  const robustness = question?.question_key === 'robustness_interference_validation'
  const supportedQuestion = inputLimit || pairedBridge || robustness || question?.question_key === 'precision_reproducibility'
  const selectedModel = options.data?.locked_models.find((item) => item.id === modelId)
  const selectedDataset = options.data?.prepared_datasets.find((item) => item.id === preparedId)
  const compatible = Boolean(selectedModel && selectedDataset?.assays.includes(selectedModel.expected_assay))

  useEffect(() => {
    if (!options.data) return
    if (!modelId && options.data.locked_models.length) setModelId(options.data.locked_models[0].id)
    if (!preparedId && options.data.prepared_datasets.length) setPreparedId(options.data.prepared_datasets[0].id)
  }, [options.data, modelId, preparedId])

  useEffect(() => {
    if (!design.data) return
    const value = (row: Record<string, string>, key: string) => row[key]?.trim() || ''
    setAssignments(design.data.metadata_rows.map((row, index) => ({
      measurement_id: row.sample_id,
      biological_sample_id: value(row, 'biological_sample_id'),
      replicate_id: value(row, 'replicate_id') || String(index + 1),
      operator: value(row, 'operator') || null,
      run: value(row, 'run') || value(row, 'sequencing_run') || null,
      reagent_lot: value(row, 'reagent_lot') || null,
      input_level: value(row, 'input_level') ? Number(value(row, 'input_level')) : value(row, 'input_ng') ? Number(value(row, 'input_ng')) : null,
      quality_metric: value(row, 'quality_metric') ? Number(value(row, 'quality_metric')) : value(row, 'dv200') ? Number(value(row, 'dv200')) : null,
      qc_failure: ['true', '1', 'yes'].includes(value(row, 'qc_failure').toLowerCase()),
      condition: value(row, 'condition') || value(row, 'method') || null,
      challenge_type: value(row, 'challenge_type') || null,
      subgroup: value(row, 'subgroup') || null,
      instrument: value(row, 'instrument') || null,
      day: value(row, 'day') || null,
      site: value(row, 'site') || null,
      include: true,
      exclusion_reason: null,
    })))
    const levels = design.data.metadata_rows.map((row) => Number(row.input_level || row.input_ng)).filter((value) => Number.isFinite(value) && value > 0)
    if (levels.length) setReferenceLevel(Math.max(...levels))
    const conditions = [...new Set(design.data.metadata_rows.map((row) => row.condition || row.method).filter((value): value is string => !!value))]
    if (conditions.length) setReferenceCondition(conditions[0])
    if (conditions.length > 1) setComparatorCondition(conditions[1])
  }, [design.data])

  useEffect(() => {
    if (!inputLimit) return
    setName('Locked endpoint input and degradation limit')
    setObjective('Evaluate locked score, call, and QC stability across paired ordered input or quality levels without retraining.')
    setFactors(['input_level', 'run'])
  }, [inputLimit])

  useEffect(() => {
    if (!pairedBridge) return
    setName('Locked endpoint paired bridge')
    setObjective('Evaluate paired bias, agreement, discordance, and equivalence for a candidate assay or pipeline change without retraining.')
    setFactors(['condition', 'run'])
  }, [pairedBridge])

  useEffect(() => {
    if (!robustness) return
    setName('Locked endpoint robustness and interference')
    setObjective('Quantify paired locked-score, call, and QC changes under a prespecified realistic challenge without retraining.')
    setFactors(['condition', 'challenge_type', 'run'])
    setReferenceCondition('reference')
    setComparatorCondition('challenge')
    setConditionRationale('The reference is the unchallenged locked assay condition and the challenge is prespecified before execution.')
  }, [robustness])

  const missingRequired = useMemo(() => assignments.filter((row) => row.include && (
    !row.biological_sample_id || (inputLimit
      ? !row.input_level || !row.run
      : pairedBridge ? !row.condition || !row.run
      : robustness ? !row.condition || !row.challenge_type || !row.run
      : !row.replicate_id || !row.operator || !row.run || !row.reagent_lot)
  )).length, [assignments, inputLimit, pairedBridge, robustness])
  const invalidExclusions = assignments.some((row) => !row.include && !row.exclusion_reason)
  const create = useMutation({
    mutationFn: () => createAnalyticalStudy({
      assay_project_id: assayProjectId,
      question_id: question!.id,
      model_id: modelId,
      prepared_dataset_id: preparedId,
      name,
      objective,
      study_type: inputLimit ? 'INPUT_DEGRADATION_LIMIT' : pairedBridge ? 'PAIRED_BRIDGING' : robustness ? 'ROBUSTNESS_INTERFERENCE' : 'PRECISION_REPRODUCIBILITY',
      assignments,
      factors,
      criteria: inputLimit ? [
        { key: 'score_stability_all_levels', metric: 'mean_absolute_score_difference', endpoint: 'classifier_score', operator: 'all_levels', threshold: scoreDifferenceThreshold, rationale: 'Prespecified maximum paired locked-score change at every tested lower level.' },
        { key: 'call_stability_consecutive', metric: 'call_agreement_to_reference', endpoint: 'predicted_class', operator: 'consecutive_levels', threshold: agreementThreshold, rationale: 'Prespecified call agreement must persist through at least two consecutive lower levels.' },
        { key: 'qc_failure_all_levels', metric: 'qc_failure_rate', endpoint: 'qc_failure', operator: 'all_levels', threshold: failureRateThreshold, rationale: 'Prespecified maximum technical QC failure rate at every tested lower level.' },
      ] : pairedBridge ? [
        { key: 'paired_bias_margin', metric: 'paired_bias', endpoint: 'classifier_score', operator: 'absolute_lte', threshold: equivalenceMargin, rationale: 'The absolute paired locked-score bias must remain within the prespecified equivalence margin.' },
        { key: 'categorical_agreement', metric: 'categorical_agreement', endpoint: 'predicted_class', operator: 'gte', threshold: agreementThreshold, rationale: 'The locked categorical call must remain concordant across the bridge.' },
        { key: 'tost_equivalence', metric: 'tost_equivalence', endpoint: 'classifier_score', operator: 'gte', threshold: 1, rationale: 'The paired confidence interval must remain within the prespecified equivalence margin.' },
      ] : robustness ? [
        { key: 'challenge_effect_margin', metric: 'mean_challenge_effect', endpoint: 'classifier_score', operator: 'absolute_lte', threshold: equivalenceMargin, rationale: 'The absolute mean locked-score challenge effect must remain within the prespecified margin.' },
        { key: 'call_change_rate', metric: 'call_change_rate', endpoint: 'predicted_class', operator: 'lte', threshold: 1 - agreementThreshold, rationale: 'The rate of challenge-associated categorical call changes must remain below the prespecified limit.' },
        { key: 'qc_failure_rate', metric: 'qc_failure_rate', endpoint: 'qc_failure', operator: 'lte', threshold: failureRateThreshold, rationale: 'The technical QC failure rate under challenge must remain below the prespecified limit.' },
      ] : [
        { key: 'score_icc', metric: 'icc', endpoint: 'classifier_score', operator: 'gte', threshold: iccThreshold, rationale: iccRationale },
        { key: 'call_agreement', metric: 'categorical_agreement', endpoint: 'predicted_class', operator: 'gte', threshold: agreementThreshold, rationale: agreementRationale },
      ],
      confidence_level: 0.95,
      bootstrap_iterations: 2000,
      threshold_proximity_band: proximityBand,
      ...(inputLimit ? { reference_level: referenceLevel, level_rationale: levelRationale } : pairedBridge || robustness ? { reference_condition: referenceCondition, comparator_condition: comparatorCondition, equivalence_margin: equivalenceMargin, condition_rationale: conditionRationale } : {}),
    }),
    onSuccess: (study) => navigate(`/studies/${study.id}`),
  })

  if (assay.isPending || questions.isPending || options.isPending) return <LoadingState label="Loading locked model and validation inputs…" />
  if (assay.isError || questions.isError || options.isError) return <ErrorState error={assay.error || questions.error || options.error} />

  return <Stack spacing={4}>
    <Link component={RouterLink} to={`/assay-development/${assayProjectId}`} underline="hover" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, width: 'fit-content' }}><ArrowBackRoundedIcon fontSize="small" /> Guided assay workspace</Link>
    <div><Typography variant="overline" color="secondary.main" fontWeight={750}>Post-lock Analytical Study</Typography><Typography variant="h3" fontWeight={760}>{inputLimit ? 'Input and degradation limit' : pairedBridge ? 'Paired bridging' : robustness ? 'Robustness and interference' : 'Precision and reproducibility'}</Typography><Typography color="text.secondary" mt={1}>Map repeated measurements, declare factors and criteria, and validate the design before freezing it. The locked classifier is applied without retraining.</Typography></div>
    {searchParams.get('recommendation') && <Alert severity="success">Recommendation accepted. This is an editable draft; no study has been launched.</Alert>}
    {!supportedQuestion && <Alert severity="error">Select an implemented validation-study scientific question in the guided workspace before creating this study.</Alert>}
    {!options.data.locked_models.length && <Alert severity="warning">No eligible locked classifier is available. Review and lock a model first.</Alert>}
    <Paper variant="outlined" sx={{ p: 3 }}><Grid container spacing={2}>
      <Grid item xs={12} md={8}><TextField fullWidth label="Study name" value={name} onChange={(event) => setName(event.target.value)} /></Grid>
      <Grid item xs={12} md={4}><TextField select fullWidth label="Locked model" value={modelId} onChange={(event) => setModelId(event.target.value)}>{options.data.locked_models.map((item) => <MenuItem key={item.id} value={item.id}>{item.name} · {item.feature_count} features</MenuItem>)}</TextField></Grid>
      <Grid item xs={12}><TextField fullWidth multiline minRows={2} label="Objective" value={objective} onChange={(event) => setObjective(event.target.value)} /></Grid>
      <Grid item xs={12}><TextField select fullWidth label="Validation Expression Bundle" value={preparedId} onChange={(event) => setPreparedId(event.target.value)}>{options.data.prepared_datasets.map((item) => <MenuItem key={item.id} value={item.id}>{item.dataset_name} · v{item.version} · {item.sample_count} measurements · {item.assays.join(', ')}</MenuItem>)}</TextField></Grid>
    </Grid></Paper>
    {!compatible && modelId && preparedId && <Alert severity="error">The selected bundle does not contain the locked model's required {selectedModel?.expected_assay} assay.</Alert>}

    <div><Typography variant="h4" fontWeight={740}>{inputLimit ? 'Ordered paired-level assignments' : pairedBridge ? 'Reference/comparator bridge assignments' : robustness ? 'Challenge/reference paired assignments' : 'Repeated-measure assignments'}</Typography><Typography color="text.secondary" mt={0.5}>Measurement identifiers come from the immutable bundle. Required design fields must be explicit; filenames are never interpreted.</Typography></div>
    {design.isPending && <LoadingState label="Reading immutable sample metadata…" />}
    {design.isError && <ErrorState error={design.error} />}
    <StudyAssignmentTable assignments={assignments} editable template={inputLimit ? 'input_limit' : pairedBridge ? 'paired_bridge' : robustness ? 'robustness' : 'precision'} onChange={setAssignments} />
    {missingRequired > 0 && <Alert severity="warning">{missingRequired} included measurement(s) still require {inputLimit ? 'biological sample, input level, and run' : pairedBridge ? 'biological sample, condition, and run' : robustness ? 'biological sample, condition, challenge type, and run' : 'biological sample, replicate, operator, run, or reagent-lot'} mapping.</Alert>}

    {!inputLimit && !pairedBridge && !robustness && <Paper variant="outlined" sx={{ p: 3 }}><Typography variant="h5" fontWeight={720}>Variance factors</Typography><Typography variant="body2" color="text.secondary">Operator and run are required for this initial template. Add only factors represented by at least two observed levels.</Typography><Stack direction="row" flexWrap="wrap" mt={1}>
      <FormControlLabel control={<Checkbox checked disabled />} label="Operator" />
      <FormControlLabel control={<Checkbox checked disabled />} label="Run" />
      {optionalFactors.map((factor) => <FormControlLabel key={factor} control={<Checkbox checked={factors.includes(factor)} onChange={(event) => setFactors((current) => event.target.checked ? [...current, factor] : current.filter((item) => item !== factor))} />} label={factor.replaceAll('_', ' ')} />)}
    </Stack></Paper>}

    <Paper variant="outlined" sx={{ p: 3 }}><Typography variant="h5" fontWeight={720}>Prespecified acceptance criteria</Typography><Alert severity="warning" sx={{ mt: 1.5, mb: 2 }}>Thresholds and rationales are frozen before execution. Missing metrics become indeterminate; they never pass silently.</Alert><Grid container spacing={2}>
      {inputLimit ? <>
        <Grid item xs={12} md={3}><TextField fullWidth type="number" label="Reference level" value={referenceLevel} onChange={(event) => setReferenceLevel(Number(event.target.value))} /></Grid>
        <Grid item xs={12} md={9}><TextField fullWidth label="Reference/level rationale" value={levelRationale} onChange={(event) => setLevelRationale(event.target.value)} /></Grid>
        <Grid item xs={12} md={3}><TextField fullWidth type="number" inputProps={{ step: 0.01, min: 0 }} label="Maximum absolute score difference" value={scoreDifferenceThreshold} onChange={(event) => setScoreDifferenceThreshold(Number(event.target.value))} /></Grid>
        <Grid item xs={12} md={3}><TextField fullWidth type="number" inputProps={{ step: 0.01, min: 0, max: 1 }} label="Minimum consecutive call agreement" value={agreementThreshold} onChange={(event) => setAgreementThreshold(Number(event.target.value))} /></Grid>
        <Grid item xs={12} md={3}><TextField fullWidth type="number" inputProps={{ step: 0.01, min: 0, max: 1 }} label="Maximum QC failure rate" value={failureRateThreshold} onChange={(event) => setFailureRateThreshold(Number(event.target.value))} /></Grid>
      </> : pairedBridge ? <>
        <Grid item xs={12} md={3}><TextField fullWidth label="Reference condition" value={referenceCondition} onChange={(event) => setReferenceCondition(event.target.value)} /></Grid>
        <Grid item xs={12} md={3}><TextField fullWidth label="Comparator condition" value={comparatorCondition} onChange={(event) => setComparatorCondition(event.target.value)} /></Grid>
        <Grid item xs={12} md={3}><TextField fullWidth type="number" inputProps={{ step: 0.01, min: 0 }} label="Equivalence margin" value={equivalenceMargin} onChange={(event) => setEquivalenceMargin(Number(event.target.value))} /></Grid>
        <Grid item xs={12} md={3}><TextField fullWidth type="number" inputProps={{ step: 0.01, min: 0, max: 1 }} label="Minimum call agreement" value={agreementThreshold} onChange={(event) => setAgreementThreshold(Number(event.target.value))} /></Grid>
        <Grid item xs={12}><TextField fullWidth label="Condition and margin rationale" value={conditionRationale} onChange={(event) => setConditionRationale(event.target.value)} /></Grid>
        <Grid item xs={12}><Alert severity="info">Correlation is reported descriptively but cannot pass equivalence on its own.</Alert></Grid>
      </> : robustness ? <>
        <Grid item xs={12} md={3}><TextField fullWidth label="Reference condition" value={referenceCondition} onChange={(event) => setReferenceCondition(event.target.value)} /></Grid>
        <Grid item xs={12} md={3}><TextField fullWidth label="Challenge condition" value={comparatorCondition} onChange={(event) => setComparatorCondition(event.target.value)} /></Grid>
        <Grid item xs={12} md={3}><TextField fullWidth type="number" inputProps={{ step: 0.01, min: 0 }} label="Maximum absolute challenge effect" value={equivalenceMargin} onChange={(event) => setEquivalenceMargin(Number(event.target.value))} /></Grid>
        <Grid item xs={12} md={3}><TextField fullWidth type="number" inputProps={{ step: 0.01, min: 0, max: 1 }} label="Minimum call stability" value={agreementThreshold} onChange={(event) => setAgreementThreshold(Number(event.target.value))} /></Grid>
        <Grid item xs={12} md={3}><TextField fullWidth type="number" inputProps={{ step: 0.01, min: 0, max: 1 }} label="Maximum QC failure rate" value={failureRateThreshold} onChange={(event) => setFailureRateThreshold(Number(event.target.value))} /></Grid>
        <Grid item xs={12} md={9}><TextField fullWidth label="Challenge and effect-margin rationale" value={conditionRationale} onChange={(event) => setConditionRationale(event.target.value)} /></Grid>
        <Grid item xs={12}><Alert severity="info">This study reports technical challenge effects and call changes. It does not support a biological-specificity claim.</Alert></Grid>
      </> : <><Grid item xs={12} md={3}><TextField fullWidth type="number" inputProps={{ step: 0.01, min: 0, max: 1 }} label="Minimum score ICC" value={iccThreshold} onChange={(event) => setIccThreshold(Number(event.target.value))} /></Grid>
      <Grid item xs={12} md={9}><TextField fullWidth label="ICC threshold rationale" value={iccRationale} onChange={(event) => setIccRationale(event.target.value)} /></Grid>
      <Grid item xs={12} md={3}><TextField fullWidth type="number" inputProps={{ step: 0.01, min: 0, max: 1 }} label="Minimum call agreement" value={agreementThreshold} onChange={(event) => setAgreementThreshold(Number(event.target.value))} /></Grid>
      <Grid item xs={12} md={9}><TextField fullWidth label="Agreement threshold rationale" value={agreementRationale} onChange={(event) => setAgreementRationale(event.target.value)} /></Grid></>}
      <Grid item xs={12} md={3}><TextField fullWidth type="number" inputProps={{ step: 0.01, min: 0, max: 1 }} label="Threshold proximity band" value={proximityBand} onChange={(event) => setProximityBand(Number(event.target.value))} /></Grid>
    </Grid></Paper>
    {create.isError && <ErrorState error={create.error} />}
    <Stack direction="row" spacing={2}><Button variant="contained" color="secondary" size="large" disabled={!supportedQuestion || !compatible || !assignments.length || missingRequired > 0 || invalidExclusions || !name.trim() || !objective.trim() || (!inputLimit && !pairedBridge && !robustness && (!iccRationale.trim() || !agreementRationale.trim())) || (inputLimit && !levelRationale.trim()) || ((pairedBridge || robustness) && (!conditionRationale.trim() || referenceCondition === comparatorCondition)) || create.isPending} onClick={() => create.mutate()}>Create draft and validate design</Button><Button component={RouterLink} to={`/assay-development/${assayProjectId}`}>Cancel</Button></Stack>
  </Stack>
}
