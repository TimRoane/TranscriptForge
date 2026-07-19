import ArrowForwardRoundedIcon from '@mui/icons-material/ArrowForwardRounded'
import {
  Alert,
  Button,
  Chip,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  createClassifierAnalysis,
  fetchClassifierDesignOptions,
  validateClassifierDesign,
  type ClassifierParameters,
  type GuidedAnalysisContext,
} from '../api/client'
import { ErrorState, LoadingState } from './ApiState'

const OUTCOME_PRIORITY = ['phenotype', 'condition', 'status', 'disease', 'treatment', 'group']
const GROUP_PRIORITY = [
  'subject_id', 'subject', 'patient_id', 'patient', 'donor_id', 'donor',
  'participant_id', 'participant', 'individual_id', 'individual',
]
const COHORT_PRIORITY = ['cohort', 'site', 'center', 'centre']
const OUTCOME_EXCLUDED = new Set([
  ...GROUP_PRIORITY,
  ...COHORT_PRIORITY,
  'sample',
  'sample_id',
  'array_id',
  'library_id',
])

function normalized(value: string) {
  return value.trim().toLowerCase().replace(/[\s-]+/g, '_')
}

export function ClassifierSetupPanel({ preparedDatasetId, guidedContext }: { preparedDatasetId: string; guidedContext?: GuidedAnalysisContext }) {
  const navigate = useNavigate()
  const [classifierMethod, setClassifierMethod] = useState<'elastic_net' | 'multinomial_elastic_net'>('elastic_net')
  const [outcomeColumn, setOutcomeColumn] = useState('')
  const [positiveClass, setPositiveClass] = useState('')
  const [groupColumn, setGroupColumn] = useState('')
  const [cohortColumn, setCohortColumn] = useState('')
  const [topVariableFeatures, setTopVariableFeatures] = useState(500)
  const [outerFolds, setOuterFolds] = useState(5)
  const [innerFolds, setInnerFolds] = useState(4)
  const [repeats, setRepeats] = useState(3)
  const [primaryMetric, setPrimaryMetric] = useState<ClassifierParameters['primary_metric']>('roc_auc')
  const [classWeight, setClassWeight] = useState<ClassifierParameters['class_weight']>('balanced')
  const [calibration, setCalibration] = useState<ClassifierParameters['probability_calibration']>('none')
  const [thresholdStrategy, setThresholdStrategy] = useState<ClassifierParameters['decision_threshold_strategy']>('fixed_0_5')
  const [bootstrapIterations, setBootstrapIterations] = useState(1000)
  const [permutationCount, setPermutationCount] = useState(100)
  const randomSeed = 20260717
  const multiclass = classifierMethod === 'multinomial_elastic_net'
  const options = useQuery({
    queryKey: ['classifier-design-options', preparedDatasetId],
    queryFn: ({ signal }) => fetchClassifierDesignOptions(preparedDatasetId, signal),
    enabled: Boolean(preparedDatasetId),
  })
  const outcomes = useMemo(
    () => options.data?.variables.filter(
      (variable) => variable.missing_count === 0 && (
        multiclass
          ? variable.unique_count >= 3 && variable.unique_count <= 20
          : variable.unique_count === 2
      ) && !OUTCOME_EXCLUDED.has(normalized(variable.name)),
    ) ?? [],
    [multiclass, options.data?.variables],
  )
  const groups = useMemo(
    () => options.data?.variables.filter(
      (variable) => variable.missing_count === 0
        && variable.unique_count >= 2
        && variable.unique_count < (options.data?.sample_count ?? 0),
    ) ?? [],
    [options.data],
  )
  const selectedOutcome = outcomes.find((item) => item.name === outcomeColumn)

  useEffect(() => {
    if (outcomes.length === 0) return
    if (!outcomes.some((item) => item.name === outcomeColumn)) {
      const preferred = OUTCOME_PRIORITY
        .map((name) => outcomes.find((item) => normalized(item.name) === name))
        .find((item) => item !== undefined) ?? outcomes[0]
      setOutcomeColumn(preferred.name)
    }
  }, [outcomeColumn, outcomes])
  useEffect(() => {
    if (!selectedOutcome || multiclass) {
      if (multiclass) setPositiveClass('')
      return
    }
    const preferred = selectedOutcome.levels.find((level) =>
      ['case', 'treated', 'disease', 'positive', 'yes', '1'].includes(level.toLowerCase()),
    ) ?? selectedOutcome.levels[1]
    if (!selectedOutcome.levels.includes(positiveClass)) setPositiveClass(preferred)
  }, [multiclass, positiveClass, selectedOutcome])
  useEffect(() => {
    if (multiclass) {
      setPrimaryMetric('macro_roc_auc')
      setCalibration('none')
      setThresholdStrategy('fixed_0_5')
    } else if (!['roc_auc', 'pr_auc', 'balanced_accuracy'].includes(primaryMetric)) {
      setPrimaryMetric('roc_auc')
    }
  }, [multiclass, primaryMetric])
  useEffect(() => {
    if (!options.data) return
    if (!groups.some((item) => item.name === groupColumn)) {
      const preferred = GROUP_PRIORITY
        .map((name) => groups.find((item) => normalized(item.name) === name))
        .find((item) => item !== undefined)
      setGroupColumn(preferred?.name ?? '')
    }
    if (!groups.some((item) => item.name === cohortColumn)) {
      const preferred = COHORT_PRIORITY
        .map((name) => groups.find((item) => normalized(item.name) === name))
        .find((item) => item !== undefined)
      setCohortColumn(preferred?.name ?? '')
    }
  }, [cohortColumn, groupColumn, groups, options.data])

  const effectivePrimaryMetric: ClassifierParameters['primary_metric'] = multiclass
    ? (['macro_roc_auc', 'macro_f1', 'balanced_accuracy'].includes(primaryMetric)
      ? primaryMetric
      : 'macro_roc_auc')
    : (['roc_auc', 'pr_auc', 'balanced_accuracy'].includes(primaryMetric)
      ? primaryMetric
      : 'roc_auc')
  const parameters: ClassifierParameters = {
    outcome_column: outcomeColumn,
    positive_class: multiclass ? null : positiveClass,
    group_column: groupColumn || null,
    cohort_column: cohortColumn || null,
    validation_mode: 'repeated_nested_cross_validation',
    feature_filter: 'top_variance',
    top_variable_features: topVariableFeatures,
    class_weight: classWeight,
    outer_folds: outerFolds,
    inner_folds: innerFolds,
    repeats,
    primary_metric: effectivePrimaryMetric,
    probability_calibration: calibration,
    decision_threshold_strategy: thresholdStrategy,
    bootstrap_iterations: bootstrapIterations,
    permutation_count: permutationCount,
  }
  const preview = useQuery({
    queryKey: [
      'classifier-design-preview', preparedDatasetId, classifierMethod, outcomeColumn, positiveClass,
      groupColumn, cohortColumn, topVariableFeatures, outerFolds, innerFolds, repeats,
      primaryMetric, classWeight, calibration, thresholdStrategy, bootstrapIterations,
      permutationCount,
    ],
    queryFn: ({ signal }) => validateClassifierDesign(preparedDatasetId, {
      assay: 'log_expression', method: classifierMethod, parameters, random_seed: randomSeed,
    }, signal),
    enabled: Boolean(
      options.data?.assays.includes('log_expression')
        && outcomeColumn
        && (multiclass || positiveClass),
    ),
  })
  const save = useMutation({
    mutationFn: () => createClassifierAnalysis(preparedDatasetId, {
      name: multiclass
        ? `${outcomeColumn} multinomial elastic-net classifier`
        : `${positiveClass} elastic-net classifier`,
      assay: 'log_expression',
      method: classifierMethod,
      parameters,
      random_seed: randomSeed,
      ...guidedContext,
    }),
    onSuccess: (analysis) => navigate(`/analyses/${analysis.id}`),
  })

  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Stack spacing={2.5}>
        <div>
          <Typography variant="overline" color="secondary.main" fontWeight={750}>
            Classifier development
          </Typography>
          <Typography variant="h5" fontWeight={700}>Design a leakage-resistant classifier</Typography>
          <Typography color="text.secondary" mt={0.5}>
            Binary and multinomial elastic-net logistic regression use repeated nested cross-validation.
            Every filter, transformation, feature selection, and hyperparameter choice is fitted
            inside training folds only.
          </Typography>
        </div>
        {options.isPending && <LoadingState label="Reading classifier design options…" />}
        {options.isError && <ErrorState error={options.error} />}
        {options.data && !options.data.assays.includes('log_expression') && (
          <Alert severity="info">
            Classifier development requires a gene-level log_expression assay in this bundle.
          </Alert>
        )}
        {options.data?.assays.includes('log_expression') && (
          <TextField select label="Classifier type" size="small" value={classifierMethod} onChange={(event) => setClassifierMethod(event.target.value as typeof classifierMethod)} sx={{ width: 'fit-content', minWidth: 220 }}>
            <MenuItem value="elastic_net">Binary elastic net</MenuItem>
            <MenuItem value="multinomial_elastic_net">Multiclass elastic net</MenuItem>
          </TextField>
        )}
        {options.data?.assays.includes('log_expression') && outcomes.length === 0 && (
          <Alert severity="warning">
            No complete {multiclass ? '3–20-level' : 'two-level'} metadata column is available as a{' '}
            {multiclass ? 'multiclass' : 'binary'} outcome.
          </Alert>
        )}
        {options.data?.assays.includes('log_expression') && outcomes.length > 0 && (
          <>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
              <TextField select label={multiclass ? 'Multiclass outcome' : 'Binary outcome'} size="small" value={outcomes.some((item) => item.name === outcomeColumn) ? outcomeColumn : ''} onChange={(event) => setOutcomeColumn(event.target.value)} sx={{ minWidth: 190 }}>
                {outcomes.map((item) => <MenuItem key={item.name} value={item.name}>{item.name}</MenuItem>)}
              </TextField>
              {!multiclass && (
                <TextField select label="Positive class" size="small" value={positiveClass} onChange={(event) => setPositiveClass(event.target.value)} sx={{ minWidth: 170 }}>
                  {(selectedOutcome?.levels ?? []).map((level) => <MenuItem key={level} value={level}>{level}</MenuItem>)}
                </TextField>
              )}
              <TextField select label="Subject / group" size="small" value={groupColumn} onChange={(event) => setGroupColumn(event.target.value)} sx={{ minWidth: 190 }}>
                <MenuItem value="">None — independent samples</MenuItem>
                {groups.filter((item) => item.name !== outcomeColumn && item.name !== cohortColumn).map((item) => <MenuItem key={item.name} value={item.name}>{item.name}</MenuItem>)}
              </TextField>
              <TextField select label="Cohort / site" size="small" value={cohortColumn} onChange={(event) => setCohortColumn(event.target.value)} sx={{ minWidth: 180 }}>
                <MenuItem value="">Not recorded</MenuItem>
                {groups.filter((item) => item.name !== outcomeColumn && item.name !== groupColumn).map((item) => <MenuItem key={item.name} value={item.name}>{item.name}</MenuItem>)}
              </TextField>
            </Stack>
            {!multiclass && <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
              <TextField select label="Probability calibration" size="small" value={calibration} onChange={(event) => setCalibration(event.target.value as ClassifierParameters['probability_calibration'])} sx={{ minWidth: 210 }}>
                <MenuItem value="none">None</MenuItem>
                <MenuItem value="sigmoid">Sigmoid · inner CV only</MenuItem>
              </TextField>
              <TextField select label="Decision threshold" size="small" value={thresholdStrategy} onChange={(event) => setThresholdStrategy(event.target.value as ClassifierParameters['decision_threshold_strategy'])} sx={{ minWidth: 220 }}>
                <MenuItem value="fixed_0_5">Fixed at 0.5</MenuItem>
                <MenuItem value="inner_cv_youden">Youden index · inner CV only</MenuItem>
              </TextField>
              <TextField label="Bootstrap iterations" type="number" size="small" value={bootstrapIterations} onChange={(event) => setBootstrapIterations(Number(event.target.value))} inputProps={{ min: 200, max: 5000 }} />
              <TextField label="Label permutations" type="number" size="small" value={permutationCount} onChange={(event) => setPermutationCount(Number(event.target.value))} inputProps={{ min: 0, max: 1000 }} />
            </Stack>}
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
              <TextField label="Top variable genes" type="number" size="small" value={topVariableFeatures} onChange={(event) => setTopVariableFeatures(Number(event.target.value))} inputProps={{ min: 10, max: 20000 }} />
              <TextField label="Outer folds" type="number" size="small" value={outerFolds} onChange={(event) => setOuterFolds(Number(event.target.value))} inputProps={{ min: 2, max: 10 }} />
              <TextField label="Inner folds" type="number" size="small" value={innerFolds} onChange={(event) => setInnerFolds(Number(event.target.value))} inputProps={{ min: 2, max: 10 }} />
              <TextField label="Repeats" type="number" size="small" value={repeats} onChange={(event) => setRepeats(Number(event.target.value))} inputProps={{ min: 1, max: 20 }} />
              <TextField select label="Primary metric" size="small" value={effectivePrimaryMetric} onChange={(event) => setPrimaryMetric(event.target.value as ClassifierParameters['primary_metric'])} sx={{ minWidth: 170 }}>
                {multiclass ? [
                  <MenuItem key="macro_roc_auc" value="macro_roc_auc">Macro ROC-AUC</MenuItem>,
                  <MenuItem key="macro_f1" value="macro_f1">Macro F1</MenuItem>,
                ] : [
                  <MenuItem key="roc_auc" value="roc_auc">ROC-AUC</MenuItem>,
                  <MenuItem key="pr_auc" value="pr_auc">PR-AUC</MenuItem>,
                ]}
                <MenuItem value="balanced_accuracy">Balanced accuracy</MenuItem>
              </TextField>
              <TextField select label="Class weighting" size="small" value={classWeight} onChange={(event) => setClassWeight(event.target.value as ClassifierParameters['class_weight'])} sx={{ minWidth: 170 }}>
                <MenuItem value="balanced">Balanced</MenuItem>
                <MenuItem value="none">None</MenuItem>
              </TextField>
            </Stack>
            {preview.isPending && <LoadingState label="Auditing nested cross-validation…" />}
            {preview.isError && <ErrorState error={preview.error} />}
            {preview.data && (
              <Paper variant="outlined" sx={{ p: 2.5, bgcolor: 'background.default' }}>
                <Stack spacing={1.5}>
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    <Chip color={preview.data.valid ? 'success' : 'error'} label={preview.data.valid ? 'Design valid' : 'Design blocked'} />
                    <Chip label={`${preview.data.eligible_sample_count} samples`} />
                    <Chip label={`${preview.data.group_count} experimental units`} />
                    <Chip label={`${preview.data.outer_folds}×${preview.data.repeats} outer folds`} />
                    <Chip label={`${preview.data.expected_oof_prediction_count} planned OOF predictions`} />
                  </Stack>
                  <Typography variant="body2">
                    <strong>Fold-local pipeline:</strong> variance filtering → standardization →
                    feature selection → inner-CV elastic-net tuning. Outer test folds are evaluation
                    only. {multiclass && 'Multiclass predictions use maximum class probability.'}
                  </Typography>
                  {preview.data.fold_plan.length > 0 && (
                    <TableContainer sx={{ maxHeight: 280 }}>
                      <Table size="small" stickyHeader aria-label="Classifier outer-fold audit">
                        <TableHead><TableRow><TableCell>Repeat / fold</TableCell><TableCell align="right">Train</TableCell><TableCell align="right">Test</TableCell><TableCell align="right">Train groups</TableCell><TableCell align="right">Test groups</TableCell><TableCell align="right">Overlap</TableCell></TableRow></TableHead>
                        <TableBody>{preview.data.fold_plan.map((fold) => (
                          <TableRow key={`${fold.repeat}-${fold.fold}`}><TableCell>{fold.repeat} / {fold.fold}</TableCell><TableCell align="right">{fold.training_sample_count}</TableCell><TableCell align="right">{fold.test_sample_count}</TableCell><TableCell align="right">{fold.training_group_count}</TableCell><TableCell align="right">{fold.test_group_count}</TableCell><TableCell align="right">{fold.group_overlap_count}</TableCell></TableRow>
                        ))}</TableBody>
                      </Table>
                    </TableContainer>
                  )}
                  {preview.data.errors.map((message) => <Alert key={message} severity="error">{message}</Alert>)}
                  {preview.data.warnings.map((message) => <Alert key={message} severity="warning">{message}</Alert>)}
                </Stack>
              </Paper>
            )}
            <div>
              <Button variant="contained" endIcon={<ArrowForwardRoundedIcon />} onClick={() => save.mutate()} disabled={!preview.data?.valid || save.isPending}>
                {save.isPending ? 'Saving classifier design…' : 'Save classifier design'}
              </Button>
              <Typography variant="body2" color="text.secondary" mt={1}>
                Opens the saved analysis page, where the frozen fold audit remains visible before
                you start the classifier run.
              </Typography>
            </div>
            {save.isError && <Alert severity="error">{save.error.message}</Alert>}
          </>
        )}
      </Stack>
    </Paper>
  )
}
