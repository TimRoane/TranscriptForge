import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded'
import Inventory2RoundedIcon from '@mui/icons-material/Inventory2Rounded'
import PlayArrowRoundedIcon from '@mui/icons-material/PlayArrowRounded'
import StopCircleRoundedIcon from '@mui/icons-material/StopCircleRounded'
import UploadFileRoundedIcon from '@mui/icons-material/UploadFileRounded'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  FormControl,
  InputLabel,
  LinearProgress,
  Link,
  MenuItem,
  Select,
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
  cancelRun,
  type Dataset,
  type DatasetFile,
  type DatasetFileRole,
  type MicroarrayAggregationMethod,
  fetchDatasetFiles,
  fetchMicroarrayIngestion,
  fetchMicroarrayPlatforms,
  fetchRawRNASeqIngestion,
  fetchRun,
  fetchRunArtifacts,
  fetchPreparationRuns,
  fetchPreparedVersions,
  fetchValidationReport,
  fetchValidationRuns,
  ingestMicroarray,
  ingestRawRNASeq,
  uploadDatasetFile,
  prepareDataset,
  validateDataset,
} from '../api/client'

const activeStates = new Set(['CREATED', 'QUEUED', 'STARTING', 'RUNNING', 'CANCELLING'])

export function DatasetCard({ dataset }: { dataset: Dataset }) {
  const queryClient = useQueryClient()
  const isRawRNASeq = dataset.source_kind === 'fastq'
  const isMicroarray = dataset.source_kind === 'affymetrix_cel'
  const usesIngestionManifest = isRawRNASeq || isMicroarray
  const [lastUpload, setLastUpload] = useState<DatasetFile | null>(null)
  const [launchedRunId, setLaunchedRunId] = useState<string | null>(null)
  const [strandedness, setStrandedness] = useState<
    'auto' | 'unstranded' | 'forward' | 'reverse'
  >('auto')
  const [microarrayPlatformId, setMicroarrayPlatformId] = useState(
    'affymetrix_hugene_1_0_st_v1',
  )
  const [aggregationMethod, setAggregationMethod] = useState<MicroarrayAggregationMethod>(
    'highest_mad',
  )
  const validationRuns = useQuery({
    queryKey: ['validation-runs', dataset.id],
    queryFn: ({ signal }) => fetchValidationRuns(dataset.id, signal),
    refetchInterval: (query) => {
      const latest = query.state.data?.[0]
      return latest && activeStates.has(latest.state) ? 1500 : false
    },
    enabled: !usesIngestionManifest,
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
  const preparationArtifacts = useQuery({
    queryKey: ['run-artifacts', preparationRunId],
    queryFn: ({ signal }) => fetchRunArtifacts(preparationRunId ?? '', signal),
    enabled: preparationRun.data?.state === 'SUCCEEDED',
  })
  const preparedVersions = useQuery({
    queryKey: ['prepared-versions', dataset.id],
    queryFn: ({ signal }) => fetchPreparedVersions(dataset.id, signal),
  })
  const datasetFiles = useQuery({
    queryKey: ['dataset-files', dataset.id],
    queryFn: ({ signal }) => fetchDatasetFiles(dataset.id, signal),
    enabled: usesIngestionManifest,
  })
  const rawIngestion = useQuery({
    queryKey: ['raw-rnaseq-ingestion', dataset.id],
    queryFn: ({ signal }) => fetchRawRNASeqIngestion(dataset.id, signal),
    enabled: isRawRNASeq,
  })
  const microarrayPlatforms = useQuery({
    queryKey: ['microarray-platforms'],
    queryFn: ({ signal }) => fetchMicroarrayPlatforms(signal),
    enabled: isMicroarray,
  })
  const microarrayIngestion = useQuery({
    queryKey: ['microarray-ingestion', dataset.id],
    queryFn: ({ signal }) => fetchMicroarrayIngestion(dataset.id, signal),
    enabled: isMicroarray,
  })
  const upload = useMutation({
    mutationFn: ({ role, files }: { role: DatasetFileRole; files: File[] }) =>
      Promise.all(files.map((file) => uploadDatasetFile(dataset.id, role, file))),
    onSuccess: async (uploaded) => {
      setLastUpload(uploaded.at(-1) ?? null)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['dataset-files', dataset.id] }),
        queryClient.invalidateQueries({ queryKey: ['raw-rnaseq-ingestion', dataset.id] }),
        queryClient.invalidateQueries({ queryKey: ['microarray-ingestion', dataset.id] }),
        queryClient.invalidateQueries({ queryKey: ['datasets', dataset.project_id] }),
      ])
    },
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
  const cancelValidation = useMutation({
    mutationFn: (id: string) => cancelRun(id),
    onSuccess: async (cancelledRun) => {
      queryClient.setQueryData(['run', cancelledRun.id], cancelledRun)
      await queryClient.invalidateQueries({ queryKey: ['validation-runs', dataset.id] })
    },
  })
  const cancelPreparation = useMutation({
    mutationFn: (id: string) => cancelRun(id),
    onSuccess: async (cancelledRun) => {
      queryClient.setQueryData(['run', cancelledRun.id], cancelledRun)
      await queryClient.invalidateQueries({ queryKey: ['preparation-runs', dataset.id] })
    },
  })
  const rawIngest = useMutation({
    mutationFn: () => ingestRawRNASeq(dataset.id, { strandedness }),
    onSuccess: async (manifest) => {
      queryClient.setQueryData(['raw-rnaseq-ingestion', dataset.id], manifest)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['dataset-files', dataset.id] }),
        queryClient.invalidateQueries({ queryKey: ['datasets', dataset.project_id] }),
      ])
    },
  })
  const microarrayIngest = useMutation({
    mutationFn: () => ingestMicroarray(dataset.id, {
      platform_id: microarrayPlatformId,
      aggregation_method: aggregationMethod,
    }),
    onSuccess: async (manifest) => {
      queryClient.setQueryData(['microarray-ingestion', dataset.id], manifest)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['dataset-files', dataset.id] }),
        queryClient.invalidateQueries({ queryKey: ['datasets', dataset.project_id] }),
      ])
    },
  })
  const selectedMicroarrayPlatform = microarrayPlatforms.data?.find(
    (platform) => platform.platform_id === microarrayPlatformId,
  )
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

  const chooseFiles = (role: DatasetFileRole) =>
    (event: ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(event.target.files ?? [])
      if (files.length) upload.mutate({ role, files })
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
          {isRawRNASeq ? (
            <Stack direction="row" spacing={1} flexWrap="wrap">
              <Button
                component="label"
                variant="outlined"
                startIcon={<UploadFileRoundedIcon />}
                disabled={upload.isPending}
              >
                R1 FASTQ
                <input
                  hidden
                  multiple
                  type="file"
                  accept=".fastq,.fq,.fastq.gz,.fq.gz"
                  onChange={chooseFiles('fastq_r1')}
                />
              </Button>
              <Button
                component="label"
                variant="outlined"
                startIcon={<UploadFileRoundedIcon />}
                disabled={upload.isPending}
              >
                R2 FASTQ
                <input
                  hidden
                  multiple
                  type="file"
                  accept=".fastq,.fq,.fastq.gz,.fq.gz"
                  onChange={chooseFiles('fastq_r2')}
                />
              </Button>
              <Button
                component="label"
                variant="outlined"
                startIcon={<UploadFileRoundedIcon />}
                disabled={upload.isPending}
              >
                Sample sheet
                <input
                  hidden
                  type="file"
                  accept=".tsv,.txt"
                  onChange={chooseFiles('sample_sheet')}
                />
              </Button>
            </Stack>
          ) : isMicroarray ? (
            <Stack direction="row" spacing={1} flexWrap="wrap">
              <Button
                component="label"
                variant="outlined"
                startIcon={<UploadFileRoundedIcon />}
                disabled={upload.isPending || isPreparing}
              >
                CEL files
                <input
                  hidden
                  multiple
                  type="file"
                  accept=".CEL,.cel,.CEL.gz,.cel.gz"
                  onChange={chooseFiles('cel_file')}
                />
              </Button>
              <Button
                component="label"
                variant="outlined"
                startIcon={<UploadFileRoundedIcon />}
                disabled={upload.isPending || isPreparing}
              >
                Sample metadata
                <input
                  hidden
                  type="file"
                  accept=".tsv,.txt"
                  onChange={chooseFiles('sample_metadata')}
                />
              </Button>
            </Stack>
          ) : (
            <Stack direction="row" spacing={1} flexWrap="wrap">
              <Button component="label" variant="outlined" startIcon={<UploadFileRoundedIcon />} disabled={upload.isPending || isActive || isPreparing}>
                Matrix
                <input hidden type="file" accept=".csv,.tsv,.txt,.gz" onChange={chooseFiles(matrixRole)} />
              </Button>
              <Button component="label" variant="outlined" startIcon={<UploadFileRoundedIcon />} disabled={upload.isPending || isActive || isPreparing}>
                Metadata
                <input hidden type="file" accept=".csv,.tsv,.txt" onChange={chooseFiles('sample_metadata')} />
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
          )}
        </Stack>
        {upload.isError && <Alert severity="error" sx={{ mt: 2 }}>{upload.error.message}</Alert>}
        {validation.isError && <Alert severity="error" sx={{ mt: 2 }}>{validation.error.message}</Alert>}
        {preparation.isError && <Alert severity="error" sx={{ mt: 2 }}>{preparation.error.message}</Alert>}
        {cancelValidation.isError && <Alert severity="error" sx={{ mt: 2 }}>{cancelValidation.error.message}</Alert>}
        {cancelPreparation.isError && <Alert severity="error" sx={{ mt: 2 }}>{cancelPreparation.error.message}</Alert>}
        {rawIngest.isError && <Alert severity="error" sx={{ mt: 2 }}>{rawIngest.error.message}</Alert>}
        {microarrayIngest.isError && <Alert severity="error" sx={{ mt: 2 }}>{microarrayIngest.error.message}</Alert>}
        {lastUpload && (
          <Alert severity="success" sx={{ mt: 2 }}>
            Uploaded {lastUpload.original_name} · SHA-256 {lastUpload.sha256.slice(0, 12)}…
          </Alert>
        )}
        {isRawRNASeq && (
          <Box mt={2}>
            <Divider sx={{ mb: 2 }} />
            <Typography fontWeight={700}>Raw RNA-seq ingestion</Typography>
            <Typography variant="body2" color="text.secondary" mt={0.5}>
              The tab-separated sample sheet requires <code>sample_id</code>, <code>read1</code>,
              and <code>read2</code> columns. Add <code>lane_id</code> and repeat a sample row for
              multi-lane libraries. Leave <code>read2</code> blank for a uniformly single-end
              dataset; metadata must agree across a sample&apos;s lanes.
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} mt={2} alignItems={{ sm: 'center' }}>
              <FormControl size="small" sx={{ minWidth: 170 }}>
                <InputLabel id={`strandedness-${dataset.id}`}>Strandedness</InputLabel>
                <Select
                  labelId={`strandedness-${dataset.id}`}
                  label="Strandedness"
                  value={strandedness}
                  onChange={(event) => setStrandedness(event.target.value as typeof strandedness)}
                >
                  <MenuItem value="auto">Auto-detect</MenuItem>
                  <MenuItem value="unstranded">Unstranded</MenuItem>
                  <MenuItem value="forward">Forward</MenuItem>
                  <MenuItem value="reverse">Reverse</MenuItem>
                </Select>
              </FormControl>
              <Button
                variant="contained"
                startIcon={<PlayArrowRoundedIcon />}
                disabled={rawIngest.isPending || upload.isPending || isPreparing}
                onClick={() => rawIngest.mutate()}
              >
                Validate sample sheet
              </Button>
              <Button
                variant="contained"
                color="secondary"
                startIcon={<Inventory2RoundedIcon />}
                disabled={
                  !rawIngestion.data || preparation.isPending || upload.isPending || isPreparing
                }
                onClick={() => preparation.mutate()}
              >
                Run QC &amp; quantify
              </Button>
              <Chip
                variant="outlined"
                label={`${datasetFiles.data?.filter((file) => file.role === 'fastq_r1').length ?? 0} R1 files`}
              />
              <Chip
                variant="outlined"
                label={`${datasetFiles.data?.filter((file) => file.role === 'fastq_r2').length ?? 0} R2 files`}
              />
            </Stack>
            <Alert severity="info" sx={{ mt: 2 }}>
              Reference: GENCODE 50, GRCh38.p14, Salmon 1.11.4, full-genome decoy index.
              Its first materialization can take tens of minutes; the completed index is stored
              outside Git and reused by every project in this deployment.
            </Alert>
            {rawIngestion.data && (
              <Stack spacing={2} mt={2}>
                <Alert severity="success">
                  VALID: {rawIngestion.data.sample_count} {rawIngestion.data.library_layout.replace('_', '-')} samples across{' '}
                  {rawIngestion.data.lane_count} lanes ·{' '}
                  {rawIngestion.data.read_file_count} checksum-frozen FASTQ files · {rawIngestion.data.strandedness} strandedness
                </Alert>
                <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: 'anywhere' }}>
                  {rawIngestion.data.reference.name}<br />
                  Reference definition SHA-256: <code>{rawIngestion.data.reference.definition_sha256}</code>
                </Typography>
                {rawIngestion.data.warnings.map((warning) => (
                  <Alert severity="warning" key={warning}>{warning}</Alert>
                ))}
                <TableContainer sx={{ maxHeight: 280 }}>
                  <Table size="small" stickyHeader aria-label="Raw RNA-seq sample sheet preview">
                    <TableHead>
                      <TableRow>
                        <TableCell>Sample</TableCell>
                        <TableCell>Lanes</TableCell>
                        <TableCell>FASTQ inputs</TableCell>
                        <TableCell>Metadata</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {rawIngestion.data.samples.slice(0, 20).map((sample) => (
                        <TableRow key={sample.sample_id}>
                          <TableCell>{sample.sample_id}</TableCell>
                          <TableCell>{sample.lanes.map((lane) => lane.lane_id).join(', ')}</TableCell>
                          <TableCell>
                            {sample.lanes.map((lane) => (
                              <div key={lane.lane_id}>
                                {lane.read1.original_name}{lane.read2 ? ` + ${lane.read2.original_name}` : ''}
                              </div>
                            ))}
                          </TableCell>
                          <TableCell>
                            {Object.entries(sample.metadata).map(([key, value]) => `${key}=${value}`).join(', ') || '—'}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Stack>
            )}
          </Box>
        )}
        {isMicroarray && (
          <Box mt={2}>
            <Divider sx={{ mb: 2 }} />
            <Typography fontWeight={700}>Raw Affymetrix CEL ingestion</Typography>
            <Typography variant="body2" color="text.secondary" mt={0.5}>
              Upload one CEL per sample plus tab-separated metadata containing exact{' '}
              <code>sample_id</code> and <code>cel_file</code> columns. Platform compatibility is
              read from each CEL header; filenames are never used to guess the array design.
            </Typography>
            <Stack
              direction={{ xs: 'column', md: 'row' }}
              spacing={1.5}
              mt={2}
              alignItems={{ md: 'center' }}
              flexWrap="wrap"
            >
              <FormControl size="small" sx={{ minWidth: 260 }}>
                <InputLabel id={`microarray-platform-${dataset.id}`}>Platform adapter</InputLabel>
                <Select
                  labelId={`microarray-platform-${dataset.id}`}
                  label="Platform adapter"
                  value={selectedMicroarrayPlatform ? microarrayPlatformId : ''}
                  onChange={(event) => {
                    const platformId = event.target.value
                    setMicroarrayPlatformId(platformId)
                    const platform = microarrayPlatforms.data?.find(
                      (candidate) => candidate.platform_id === platformId,
                    )
                    if (platform) setAggregationMethod(platform.aggregation.default_method)
                  }}
                >
                  {microarrayPlatforms.data?.map((platform) => (
                    <MenuItem key={platform.platform_id} value={platform.platform_id}>
                      {platform.array_design}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 210 }}>
                <InputLabel id={`microarray-aggregation-${dataset.id}`}>Probe aggregation</InputLabel>
                <Select
                  labelId={`microarray-aggregation-${dataset.id}`}
                  label="Probe aggregation"
                  value={aggregationMethod}
                  onChange={(event) => setAggregationMethod(
                    event.target.value as MicroarrayAggregationMethod,
                  )}
                >
                  {(selectedMicroarrayPlatform?.aggregation.supported_methods ?? [
                    'highest_mad', 'median', 'mean',
                  ]).map((method) => (
                    <MenuItem key={method} value={method}>
                      {method === 'highest_mad' ? 'Highest MAD representative' : `${method} across probes`}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Button
                variant="contained"
                startIcon={<PlayArrowRoundedIcon />}
                disabled={
                  microarrayIngest.isPending || upload.isPending || isPreparing
                  || microarrayPlatforms.isPending
                }
                onClick={() => microarrayIngest.mutate()}
              >
                Validate CEL inputs
              </Button>
              <Button
                variant="contained"
                color="secondary"
                startIcon={<Inventory2RoundedIcon />}
                disabled={
                  !microarrayIngestion.data || preparation.isPending || upload.isPending
                  || isPreparing
                }
                onClick={() => preparation.mutate()}
              >
                Run RMA &amp; prepare
              </Button>
              <Chip
                variant="outlined"
                label={`${datasetFiles.data?.filter((file) => file.role === 'cel_file').length ?? 0} CEL files`}
              />
            </Stack>
            {microarrayPlatforms.isError && (
              <Alert severity="error" sx={{ mt: 2 }}>{microarrayPlatforms.error.message}</Alert>
            )}
            {selectedMicroarrayPlatform && (
              <Alert severity="info" sx={{ mt: 2 }}>
                {selectedMicroarrayPlatform.vendor} {selectedMicroarrayPlatform.array_design} ·{' '}
                {selectedMicroarrayPlatform.normalization.engine}{' '}
                {selectedMicroarrayPlatform.normalization.method.toUpperCase()} · annotation{' '}
                {selectedMicroarrayPlatform.annotation.package}
              </Alert>
            )}
            {!microarrayIngestion.data
              && (datasetFiles.data?.some((file) => file.role === 'cel_file') ?? false) && (
              <Alert severity="warning" sx={{ mt: 2 }}>
                CEL inputs are not currently frozen in a valid ingestion manifest. Validate again
                after every CEL or metadata upload before running RMA.
              </Alert>
            )}
            {microarrayIngestion.data && (
              <Stack spacing={2} mt={2}>
                <Alert severity="success">
                  VALID: {microarrayIngestion.data.sample_count} samples and{' '}
                  {microarrayIngestion.data.cel_file_count} checksum-frozen CEL files · detected{' '}
                  {microarrayIngestion.data.platform.detected_chip_type} ({microarrayIngestion.data.platform.cel_format})
                </Alert>
                <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: 'anywhere' }}>
                  Adapter {microarrayIngestion.data.platform.adapter_version} · RMA target{' '}
                  {microarrayIngestion.data.platform.normalization.target} · aggregation{' '}
                  {microarrayIngestion.data.aggregation_method.replace('_', ' ')}<br />
                  Platform definition SHA-256:{' '}
                  <code>{microarrayIngestion.data.platform.definition_sha256}</code>
                </Typography>
                {microarrayIngestion.data.warnings.map((warning) => (
                  <Alert severity="warning" key={warning}>{warning}</Alert>
                ))}
                <TableContainer sx={{ maxHeight: 280 }}>
                  <Table size="small" stickyHeader aria-label="Affymetrix CEL sample metadata preview">
                    <TableHead>
                      <TableRow>
                        <TableCell>Sample</TableCell>
                        <TableCell>CEL input</TableCell>
                        <TableCell>Metadata</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {microarrayIngestion.data.samples.slice(0, 20).map((sample) => (
                        <TableRow key={sample.sample_id}>
                          <TableCell>{sample.sample_id}</TableCell>
                          <TableCell>{sample.cel_file.original_name}</TableCell>
                          <TableCell>
                            {Object.entries(sample.metadata)
                              .map(([key, value]) => `${key}=${value}`).join(', ') || '—'}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Stack>
            )}
          </Box>
        )}
        {run.data && (
          <Box mt={2}>
            <Divider sx={{ mb: 2 }} />
            <Stack direction="row" justifyContent="space-between" alignItems="center" gap={2}>
              <Typography fontWeight={650}>Validation run</Typography>
              <Stack direction="row" spacing={1} alignItems="center">
                <Chip
                  size="small"
                  label={run.data.state}
                  color={run.data.state === 'FAILED' ? 'error' : run.data.state === 'SUCCEEDED' ? 'success' : 'info'}
                />
                {isActive && (
                  <Button
                    size="small"
                    color="error"
                    variant="outlined"
                    startIcon={<StopCircleRoundedIcon />}
                    disabled={cancelValidation.isPending || run.data.state === 'CANCELLING'}
                    onClick={() => cancelValidation.mutate(run.data.id)}
                  >
                    {run.data.state === 'CANCELLING' ? 'Stopping…' : 'Stop run'}
                  </Button>
                )}
              </Stack>
            </Stack>
            {isActive && <LinearProgress aria-label="Validation in progress" sx={{ mt: 1.5 }} />}
            {run.data.error_summary && <Alert severity={run.data.state === 'CANCELLED' ? 'info' : 'error'} sx={{ mt: 1.5 }}>{run.data.error_summary}</Alert>}
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
              <Stack direction="row" spacing={1} alignItems="center">
                <Chip
                  size="small"
                  label={preparationRun.data.state}
                  color={preparationRun.data.state === 'FAILED' ? 'error' : preparationRun.data.state === 'SUCCEEDED' ? 'success' : 'info'}
                />
                {isPreparing && (
                  <Button
                    size="small"
                    color="error"
                    variant="outlined"
                    startIcon={<StopCircleRoundedIcon />}
                    disabled={cancelPreparation.isPending || preparationRun.data.state === 'CANCELLING'}
                    onClick={() => cancelPreparation.mutate(preparationRun.data.id)}
                  >
                    {preparationRun.data.state === 'CANCELLING' ? 'Stopping…' : 'Stop run'}
                  </Button>
                )}
              </Stack>
            </Stack>
            {isPreparing && <LinearProgress aria-label="Preparation in progress" sx={{ mt: 1.5 }} />}
            {preparationRun.data.error_summary && <Alert severity={preparationRun.data.state === 'CANCELLED' ? 'info' : 'error'} sx={{ mt: 1.5 }}>{preparationRun.data.error_summary}</Alert>}
            {preparationArtifacts.data && (
              <Stack direction="row" spacing={2} mt={2} flexWrap="wrap">
                {preparationArtifacts.data
                  .filter((artifact) => [
                    'multiqc_report',
                    'gene_counts',
                    'gene_tpm',
                    'gene_effective_length',
                    'transcript_counts',
                    'transcript_tpm',
                    'transcript_effective_length',
                    'salmon_quantifications',
                    'raw_rnaseq_qc_metrics',
                    'microarray_gene_expression',
                    'microarray_probe_expression',
                    'microarray_probe_mapping',
                    'microarray_qc_metrics',
                    'microarray_raw_boxplot',
                    'microarray_normalized_boxplot',
                    'microarray_pca',
                    'microarray_sample_correlation',
                  ].includes(artifact.artifact_type))
                  .map((artifact) => (
                    <Link key={artifact.id} href={artifactDownloadUrl(artifact.id)} underline="hover" sx={{ display: 'inline-flex', gap: 0.5, alignItems: 'center' }}>
                      <DownloadRoundedIcon fontSize="small" /> {artifact.title}
                    </Link>
                  ))}
              </Stack>
            )}
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
