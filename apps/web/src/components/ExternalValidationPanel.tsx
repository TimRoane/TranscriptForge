import ArrowForwardRoundedIcon from '@mui/icons-material/ArrowForwardRounded'
import VerifiedRoundedIcon from '@mui/icons-material/VerifiedRounded'
import { Box, Button, Card, CardContent, Chip, Stack, Typography } from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { Link as RouterLink } from 'react-router-dom'

import { fetchProjectClassifierExternalValidations } from '../api/client'
import { ErrorState, LoadingState } from './ApiState'

export function ExternalValidationPanel({ projectId }: { projectId: string }) {
  const studies = useQuery({
    queryKey: ['classifier-external-validations', projectId],
    queryFn: ({ signal }) => fetchProjectClassifierExternalValidations(projectId, signal),
    enabled: !!projectId,
  })

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1} alignItems="center">
        <VerifiedRoundedIcon color="secondary" />
        <Typography variant="h5" fontWeight={700}>Classifier validation studies</Typography>
      </Stack>
      {studies.isPending && <LoadingState label="Loading validation studies…" />}
      {studies.isError && <ErrorState error={studies.error} />}
      {studies.data?.length === 0 && (
        <Typography color="text.secondary">No external classifier validations imported.</Typography>
      )}
      {studies.data?.map((study) => {
        const passed = study.status === 'SUCCESS_CRITERIA_MET'
        const interval = study.result.confidence_intervals.metrics.roc_auc
        return (
          <Card variant="outlined" key={study.id}>
            <CardContent>
              <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" gap={2}>
                <Box>
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Typography variant="h6" fontWeight={700}>{study.name}</Typography>
                    <Chip
                      size="small"
                      color={passed ? 'success' : 'warning'}
                      label={passed ? 'Criteria met' : 'Criteria not met'}
                    />
                    <Chip size="small" variant="outlined" label="Frozen one-shot study" />
                  </Stack>
                  <Typography color="text.secondary" mt={0.75}>
                    {study.development_accession} development → {study.external_accession} external validation
                  </Typography>
                  <Typography mt={1}>
                    External ROC-AUC {study.result.metrics.roc_auc.toFixed(3)} · 95% CI {interval.lower.toFixed(3)}–{interval.upper.toFixed(3)} · n={study.result.sample_count}
                  </Typography>
                </Box>
                <Button
                  component={RouterLink}
                  to={`/classifier-external-validations/${study.id}`}
                  endIcon={<ArrowForwardRoundedIcon />}
                  sx={{ alignSelf: { md: 'center' }, whiteSpace: 'nowrap' }}
                >
                  Open results dashboard
                </Button>
              </Stack>
            </CardContent>
          </Card>
        )
      })}
    </Stack>
  )
}
