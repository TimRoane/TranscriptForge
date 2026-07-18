import ArrowBackRoundedIcon from '@mui/icons-material/ArrowBackRounded'
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded'
import LockRoundedIcon from '@mui/icons-material/LockRounded'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  LinearProgress,
  Link,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { Link as RouterLink, useParams } from 'react-router-dom'

import {
  classifierExternalValidationArtifactUrl,
  fetchClassifierExternalValidation,
} from '../api/client'
import { ErrorState, LoadingState } from '../components/ApiState'

function metric(value: number) {
  return value.toFixed(3)
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      <CardContent>
        <Typography variant="overline" color="text.secondary" fontWeight={700}>{label}</Typography>
        <Typography variant="h4" fontWeight={750} mt={0.5}>{value}</Typography>
        <Typography color="text.secondary" variant="body2" mt={0.75}>{detail}</Typography>
      </CardContent>
    </Card>
  )
}

export function ExternalValidationPage() {
  const { validationId = '' } = useParams()
  const study = useQuery({
    queryKey: ['classifier-external-validation', validationId],
    queryFn: ({ signal }) => fetchClassifierExternalValidation(validationId, signal),
    enabled: !!validationId,
  })

  if (study.isPending) return <LoadingState label="Loading external validation…" />
  if (study.isError) return <ErrorState error={study.error} />

  const data = study.data
  const result = data.result
  const rocInterval = result.confidence_intervals.metrics.roc_auc
  const passed = result.success.passed
  const comparison = [
    {
      cohort: `${data.development_accession} development`,
      samples: data.development_summary.sample_count,
      roc: data.development_summary.roc_auc,
      lower: data.development_summary.roc_auc_lower,
      upper: data.development_summary.roc_auc_upper,
      pr: data.development_summary.pr_auc,
    },
    {
      cohort: `${data.external_accession} external`,
      samples: result.sample_count,
      roc: result.metrics.roc_auc,
      lower: rocInterval.lower,
      upper: rocInterval.upper,
      pr: result.metrics.pr_auc,
    },
  ]

  return (
    <Stack spacing={3}>
      <Link
        component={RouterLink}
        to={`/projects/${data.project_id}`}
        underline="hover"
        sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, width: 'fit-content' }}
      >
        <ArrowBackRoundedIcon fontSize="small" /> Back to project
      </Link>

      <Paper
        elevation={0}
        sx={{ p: { xs: 3, md: 4 }, color: 'common.white', background: 'linear-gradient(130deg, #0f4c5c, #4c1d95)' }}
      >
        <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" gap={2}>
          <Box>
            <Typography variant="overline" sx={{ color: 'rgba(255,255,255,0.75)' }} fontWeight={750}>
              One-shot external classifier validation
            </Typography>
            <Typography variant="h3" component="h1" fontWeight={780} mt={0.5}>{data.name}</Typography>
            <Typography mt={1} sx={{ color: 'rgba(255,255,255,0.82)' }}>
              {data.development_accession} model development → {data.external_accession} independent evaluation
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} alignItems="flex-start" flexWrap="wrap" useFlexGap>
            <Chip icon={<LockRoundedIcon />} label="Protocol frozen" sx={{ bgcolor: 'common.white' }} />
            <Chip
              label={passed ? 'Success criteria met' : 'Success criteria not met'}
              color={passed ? 'success' : 'warning'}
            />
          </Stack>
        </Stack>
      </Paper>

      <Alert severity={passed ? 'success' : 'warning'}>
        {passed
          ? 'The prespecified external success criteria were met.'
          : 'The prespecified point-estimate criterion was not met. The result remains scientifically informative and is reported without retuning or cohort replacement.'}
      </Alert>

      <Grid container spacing={2}>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard label="External ROC-AUC" value={metric(result.metrics.roc_auc)} detail={`95% CI ${metric(rocInterval.lower)}–${metric(rocInterval.upper)}`} />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard label="PR-AUC" value={metric(result.metrics.pr_auc)} detail={`Prevalence ${metric(result.metrics.prevalence)}`} />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard label="Balanced accuracy" value={metric(result.metrics.balanced_accuracy)} detail={`Sensitivity ${metric(result.metrics.sensitivity)}`} />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard label="Brier score" value={metric(result.metrics.brier_score)} detail="Lower is better; probability error" />
        </Grid>
      </Grid>

      <Grid container spacing={3}>
        <Grid item xs={12} md={7}>
          <Paper variant="outlined" sx={{ p: 3, height: '100%' }}>
            <Typography variant="h5" fontWeight={700}>Development-to-external transport</Typography>
            <Typography color="text.secondary" mt={0.5}>Nested cross-validation is shown beside the untouched external cohort.</Typography>
            <Stack spacing={2.5} mt={3}>
              {comparison.map((row) => (
                <Box key={row.cohort}>
                  <Stack direction="row" justifyContent="space-between" mb={0.75}>
                    <Typography fontWeight={650}>{row.cohort}</Typography>
                    <Typography>{metric(row.roc)}</Typography>
                  </Stack>
                  <LinearProgress variant="determinate" value={row.roc * 100} sx={{ height: 10, borderRadius: 5 }} />
                  <Typography variant="caption" color="text.secondary">95% CI {metric(row.lower)}–{metric(row.upper)} · n={row.samples} · PR-AUC {metric(row.pr)}</Typography>
                </Box>
              ))}
            </Stack>
          </Paper>
        </Grid>
        <Grid item xs={12} md={5}>
          <Paper variant="outlined" sx={{ p: 3, height: '100%' }}>
            <Typography variant="h5" fontWeight={700}>Prespecified criteria</Typography>
            <TableContainer sx={{ mt: 1.5 }}>
              <Table size="small" aria-label="Prespecified success criteria">
                <TableHead><TableRow><TableCell>Criterion</TableCell><TableCell align="right">Observed</TableCell><TableCell>Status</TableCell></TableRow></TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>ROC-AUC ≥ {metric(result.success.minimum_point_estimate)}</TableCell>
                    <TableCell align="right">{metric(result.metrics.roc_auc)}</TableCell>
                    <TableCell><Chip size="small" color={result.success.point_estimate_passed ? 'success' : 'warning'} label={result.success.point_estimate_passed ? 'Pass' : 'Not met'} /></TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Lower CI ≥ {metric(result.success.minimum_lower_confidence_bound)}</TableCell>
                    <TableCell align="right">{metric(rocInterval.lower)}</TableCell>
                    <TableCell><Chip size="small" color={result.success.lower_bound_passed ? 'success' : 'warning'} label={result.success.lower_bound_passed ? 'Pass' : 'Not met'} /></TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Grid>
      </Grid>

      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography variant="h5" fontWeight={700}>External cohort and locked predictions</Typography>
        <Grid container spacing={3} mt={0.25}>
          <Grid item xs={6} sm={3}><Typography color="text.secondary" variant="body2">Samples</Typography><Typography variant="h6" fontWeight={700}>{result.sample_count}</Typography></Grid>
          <Grid item xs={6} sm={3}><Typography color="text.secondary" variant="body2">{data.protocol.endpoint.positive_class}</Typography><Typography variant="h6" fontWeight={700}>{result.class_counts.positive}</Typography></Grid>
          <Grid item xs={6} sm={3}><Typography color="text.secondary" variant="body2">{data.protocol.endpoint.negative_class}</Typography><Typography variant="h6" fontWeight={700}>{result.class_counts.negative}</Typography></Grid>
          <Grid item xs={6} sm={3}><Typography color="text.secondary" variant="body2">Specificity</Typography><Typography variant="h6" fontWeight={700}>{metric(result.metrics.specificity)}</Typography></Grid>
        </Grid>
        {data.prediction_summary && (
          <Typography color="text.secondary" mt={2}>
            At the model’s locked threshold of {metric(data.prediction_summary.decision_threshold)}, {data.prediction_summary.predicted_positive_count} samples were predicted {data.prediction_summary.positive_class} and {data.prediction_summary.predicted_negative_count} were predicted {data.prediction_summary.negative_class}.
          </Typography>
        )}
        <Typography color="text.secondary" mt={1}>
          Calibration intercept {metric(result.metrics.calibration_intercept)} · calibration slope {metric(result.metrics.calibration_slope)} · {result.confidence_intervals.iterations.toLocaleString()} deterministic bootstrap iterations
        </Typography>
      </Paper>

      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography variant="h5" fontWeight={700}>Frozen protocol and provenance</Typography>
        <Typography mt={1}>{data.protocol.intended_use}</Typography>
        <Typography color="text.secondary" mt={1}>Protocol {data.protocol_id} · frozen {new Date(data.protocol.frozen_at).toLocaleString()}</Typography>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap mt={2}>
          {data.artifacts.map((artifact) => (
            <Button
              component="a"
              href={classifierExternalValidationArtifactUrl(data.id, artifact.name)}
              startIcon={<DownloadRoundedIcon />}
              key={artifact.name}
            >
              {artifact.title}
            </Button>
          ))}
        </Stack>
        <Alert severity="info" icon={<LockRoundedIcon />} sx={{ mt: 2 }}>
          This record is immutable. It has no rerun or tuning controls because external outcomes were revealed after the model and protocol were locked.
        </Alert>
      </Paper>
    </Stack>
  )
}
