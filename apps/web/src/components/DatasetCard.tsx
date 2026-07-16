import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded'
import Inventory2RoundedIcon from '@mui/icons-material/Inventory2Rounded'
import PlayArrowRoundedIcon from '@mui/icons-material/PlayArrowRounded'
import UploadFileRoundedIcon from '@mui/icons-material/UploadFileRounded'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  LinearProgress,
  Link,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type ChangeEvent, useEffect, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'

import {
  artifactDownloadUrl,
  type Dataset,
  type DatasetFile,
  fetchRun,
  fetchRunArtifacts,
  fetchPreparationRuns,
  fetchPreparedVersions,
  fetchValidationReport,
  fetchValidationRuns,
  uploadDatasetFile,
  prepareDataset,
  validateDataset,
} from '../api/client'

const activeStates = new Set(['CREATED', 'QUEUED', 'STARTING', 'RUNNING'])

export function DatasetCard({ dataset }: { dataset: Dataset }) {
  const queryClient = useQueryClient()
  const [lastUpload, setLastUpload] = useState<DatasetFile | null>(null)
  const [launchedRunId, setLaunchedRunId] = useState<string | null>(null)
  const validationRuns = useQuery({
    queryKey: ['validation-runs', dataset.id],
    queryFn: ({ signal }) => fetchValidationRuns(dataset.id, signal),
    refetchInterval: (query) => {
      const latest = query.state.data?.[0]
      return latest && activeStates.has(latest.state) ? 1500 : false
    },
  })
  const runId = launchedRunId ?? validationRuns.data?.[0]?.id ?? null
  const run = useQuery({
    queryKey: ['run', runId],
    queryFn: ({ signal }) => fetchRun(runId ?? '', signal),
    enabled: Boolean(runId),
    refetchInterval: (query) =>
      query.state.data && activeStates.has(query.state.data.state) ? 1500 : false,
  })
  const report = useQuery({
    queryKey: ['validation-report', runId],
    queryFn: ({ signal }) => fetchValidationReport(runId ?? '', signal),
    enabled: run.data?.state === 'SUCCEEDED',
  })
  const artifacts = useQuery({
    queryKey: ['run-artifacts', runId],
    queryFn: ({ signal }) => fetchRunArtifacts(runId ?? '', signal),
    enabled: run.data?.state === 'SUCCEEDED',
  })
  const preparationRuns = useQuery({
    queryKey: ['preparation-runs', dataset.id],
    queryFn: ({ signal }) => fetchPreparationRuns(dataset.id, signal),
    refetchInterval: (query) => {
      const latest = query.state.data?.[0]
      return latest && activeStates.has(latest.state) ? 1500 : false
    },
  })
  const preparationRunId = preparationRuns.data?.[0]?.id ?? null
  const preparationRun = useQuery({
    queryKey: ['run', preparationRunId],
    queryFn: ({ signal }) => fetchRun(preparationRunId ?? '', signal),
    enabled: Boolean(preparationRunId),
    refetchInterval: (query) =>
      query.state.data && activeStates.has(query.state.data.state) ? 1500 : false,
  })
  const preparedVersions = useQuery({
    queryKey: ['prepared-versions', dataset.id],
    queryFn: ({ signal }) => fetchPreparedVersions(dataset.id, signal),
  })
  const upload = useMutation({
    mutationFn: ({ role, file }: { role: 'count_matrix' | 'expression_matrix' | 'sample_metadata'; file: File }) =>
      uploadDatasetFile(dataset.id, role, file),
    onSuccess: setLastUpload,
  })
  const validation = useMutation({
    mutationFn: () => validateDataset(dataset.id),
    onSuccess: async (createdRun) => {
      setLaunchedRunId(createdRun.id)
      queryClient.setQueryData(['run', createdRun.id], createdRun)
      await queryClient.invalidateQueries({ queryKey: ['validation-runs', dataset.id] })
    },
  })
  const preparation = useMutation({
    mutationFn: () => prepareDataset(dataset.id),
    onSuccess: async (createdRun) => {
      queryClient.setQueryData(['run', createdRun.id], createdRun)
      await queryClient.invalidateQueries({ queryKey: ['preparation-runs', dataset.id] })
    },
  })
  const matrixRole = dataset.source_kind === 'count_matrix' ? 'count_matrix' : 'expression_matrix'
  const isActive = Boolean(run.data && activeStates.has(run.data.state))
  const isPreparing = Boolean(
    preparationRun.data && activeStates.has(preparationRun.data.state),
  )

  useEffect(() => {
    if (run.data && !activeStates.has(run.data.state)) {
      void queryClient.invalidateQueries({ queryKey: ['datasets', dataset.project_id] })
    }
  }, [dataset.project_id, queryClient, run.data])

  useEffect(() => {
    if (preparationRun.data && !activeStates.has(preparationRun.data.state)) {
      void queryClient.invalidateQueries({ queryKey: ['datasets', dataset.project_id] })
      void queryClient.invalidateQueries({ queryKey: ['prepared-versions', dataset.id] })
    }
  }, [dataset.id, dataset.project_id, preparationRun.data, queryClient])

  const chooseFile = (role: 'count_matrix' | 'expression_matrix' | 'sample_metadata') =>
    (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0]
      if (file) upload.mutate({ role, file })
      event.target.value = ''
    }

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={2}>
          <div>
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="h6">{dataset.name}</Typography>
              <Chip label={dataset.status} size="small" />
            </Stack>
            <Typography variant="body2" color="text.secondary" mt={0.5}>
              {dataset.modality.replaceAll('_', ' ')} · {dataset.source_kind.replaceAll('_', ' ')} · {dataset.genome_build ?? 'GRCh38'}
            </Typography>
          </div>
          <Stack direction="row" spacing={1} flexWrap="wrap">
            <Button component="label" variant="outlined" startIcon={<UploadFileRoundedIcon />} disabled={upload.isPending || isActive || isPreparing}>
              Matrix
              <input hidden type="file" accept=".csv,.tsv,.txt,.gz" onChange={chooseFile(matrixRole)} />
            </Button>
            <Button component="label" variant="outlined" startIcon={<UploadFileRoundedIcon />} disabled={upload.isPending || isActive || isPreparing}>
              Metadata
              <input hidden type="file" accept=".csv,.tsv,.txt" onChange={chooseFile('sample_metadata')} />
            </Button>
            <Button
              variant="contained"
              startIcon={<PlayArrowRoundedIcon />}
              disabled={validation.isPending || isActive || isPreparing}
              onClick={() => validation.mutate()}
            >
              Validate
            </Button>
            <Button
              variant="contained"
              color="secondary"
              startIcon={<Inventory2RoundedIcon />}
              disabled={
                preparation.isPending ||
                isActive ||
                isPreparing ||
                report.data?.status !== 'VALID'
              }
              onClick={() => preparation.mutate()}
            >
              Prepare
            </Button>
          </Stack>
        </Stack>
        {upload.isError && <Alert severity="error" sx={{ mt: 2 }}>{upload.error.message}</Alert>}
        {validation.isError && <Alert severity="error" sx={{ mt: 2 }}>{validation.error.message}</Alert>}
        {preparation.isError && <Alert severity="error" sx={{ mt: 2 }}>{preparation.error.message}</Alert>}
        {lastUpload && (
          <Alert severity="success" sx={{ mt: 2 }}>
            Uploaded {lastUpload.original_name} · SHA-256 {lastUpload.sha256.slice(0, 12)}…
          </Alert>
        )}
        {run.data && (
          <Box mt={2}>
            <Divider sx={{ mb: 2 }} />
            <Stack direction="row" justifyContent="space-between" alignItems="center" gap={2}>
              <Typography fontWeight={650}>Validation run</Typography>
              <Chip
                size="small"
                label={run.data.state}
                color={run.data.state === 'FAILED' ? 'error' : run.data.state === 'SUCCEEDED' ? 'success' : 'info'}
              />
            </Stack>
            {isActive && <LinearProgress aria-label="Validation in progress" sx={{ mt: 1.5 }} />}
            {run.data.error_summary && <Alert severity="error" sx={{ mt: 1.5 }}>{run.data.error_summary}</Alert>}
          </Box>
        )}
        {report.data && (
          <Box mt={2}>
            <Alert severity={report.data.status === 'VALID' ? 'success' : 'error'}>
              {report.data.status}: {report.data.matrix.feature_count.toLocaleString()} features and{' '}
              {report.data.matrix.sample_count.toLocaleString()} samples · {report.data.matrix.orientation.replaceAll('_', ' ')}
            </Alert>
            {report.data.findings.length > 0 && (
              <Stack spacing={1} mt={1.5}>
                {report.data.findings.slice(0, 10).map((finding, index) => (
                  <Alert severity={finding.severity === 'ERROR' ? 'error' : 'warning'} key={`${finding.code}-${index}`}>
                    <strong>{finding.code}</strong>: {finding.message}{finding.location ? ` (${finding.location})` : ''}
                  </Alert>
                ))}
              </Stack>
            )}
            {report.data.preview.matrix_rows.length > 0 && (
              <TableContainer sx={{ mt: 2, maxHeight: 280 }}>
                <Table size="small" stickyHeader aria-label="Matrix orientation preview">
                  <TableHead>
                    <TableRow>
                      <TableCell>ID</TableCell>
                      {Object.keys(report.data.preview.matrix_rows[0].values).map((column) => <TableCell key={column}>{column}</TableCell>)}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {report.data.preview.matrix_rows.map((row) => (
                      <TableRow key={row.id}>
                        <TableCell>{row.id}</TableCell>
                        {Object.values(row.values).map((value, index) => <TableCell key={index}>{value}</TableCell>)}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
            <Stack direction="row" spacing={2} mt={2} flexWrap="wrap">
              {artifacts.data?.filter((artifact) => ['validation_report', 'dataset_manifest'].includes(artifact.artifact_type)).map((artifact) => (
                <Link key={artifact.id} href={artifactDownloadUrl(artifact.id)} underline="hover" sx={{ display: 'inline-flex', gap: 0.5, alignItems: 'center' }}>
                  <DownloadRoundedIcon fontSize="small" /> {artifact.title}
                </Link>
              ))}
            </Stack>
          </Box>
        )}
        {preparationRun.data && (
          <Box mt={2}>
            <Divider sx={{ mb: 2 }} />
            <Stack direction="row" justifyContent="space-between" alignItems="center" gap={2}>
              <Typography fontWeight={650}>Expression Bundle preparation</Typography>
              <Chip
                size="small"
                label={preparationRun.data.state}
                color={preparationRun.data.state === 'FAILED' ? 'error' : preparationRun.data.state === 'SUCCEEDED' ? 'success' : 'info'}
              />
            </Stack>
            {isPreparing && <LinearProgress aria-label="Preparation in progress" sx={{ mt: 1.5 }} />}
            {preparationRun.data.error_summary && <Alert severity="error" sx={{ mt: 1.5 }}>{preparationRun.data.error_summary}</Alert>}
          </Box>
        )}
        {preparedVersions.data?.[0] && (
          <Alert severity="success" sx={{ mt: 2 }}>
            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} gap={1}>
              <span>
                Expression Bundle v{preparedVersions.data[0].version} · {preparedVersions.data[0].feature_count.toLocaleString()} features · {preparedVersions.data[0].sample_count.toLocaleString()} samples · QC {preparedVersions.data[0].qc_status}
              </span>
              <Button component={RouterLink} to={`/prepared-datasets/${preparedVersions.data[0].id}`} size="small" color="success">
                View prepared dataset
              </Button>
            </Stack>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}
