import ArrowBackRoundedIcon from '@mui/icons-material/ArrowBackRounded'
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded'
import LockRoundedIcon from '@mui/icons-material/LockRounded'
import VerifiedRoundedIcon from '@mui/icons-material/VerifiedRounded'
import { Alert, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Grid, Link, Paper, Stack, TextField, Typography } from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom'

import { checkModelIntegrity, cloneModel, fetchModel, fetchModelLockReadiness, lockModel, modelManifestUrl, modelPackageUrl, retireModel, reviewModel } from '../api/client'
import { ErrorState, LoadingState } from '../components/ApiState'

type Decision = 'review' | 'lock' | 'retire'

export function ModelPage() {
  const { modelId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [decision, setDecision] = useState<Decision | null>(null)
  const [rationale, setRationale] = useState('')
  const model = useQuery({ queryKey: ['model', modelId], queryFn: ({ signal }) => fetchModel(modelId, signal), enabled: !!modelId })
  const readiness = useQuery({ queryKey: ['model-readiness', modelId], queryFn: ({ signal }) => fetchModelLockReadiness(modelId, signal), enabled: !!modelId })
  const refresh = async () => { await Promise.all([queryClient.invalidateQueries({ queryKey: ['model', modelId] }), queryClient.invalidateQueries({ queryKey: ['model-readiness', modelId] }), queryClient.invalidateQueries({ queryKey: ['analysis-models'] })]) }
  const transition = useMutation({ mutationFn: () => decision === 'review' ? reviewModel(modelId, rationale) : decision === 'lock' ? lockModel(modelId, rationale) : retireModel(modelId, rationale), onSuccess: async () => { setDecision(null); setRationale(''); await refresh() } })
  const clone = useMutation({ mutationFn: () => cloneModel(modelId), onSuccess: (result) => navigate(`/models/${result.id}`) })
  const integrity = useMutation({ mutationFn: () => checkModelIntegrity(modelId) })
  if (model.isPending || readiness.isPending) return <LoadingState label="Loading model registry record…" />
  if (model.isError || readiness.isError) return <ErrorState error={model.error || readiness.error} />
  const item = model.data
  return <Stack spacing={4}>
    <Link component={RouterLink} to={`/analyses/${item.analysis_id}`} underline="hover" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, width: 'fit-content' }}><ArrowBackRoundedIcon fontSize="small" /> Classifier results</Link>
    <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" gap={2}><div><Typography variant="overline" color="secondary.main" fontWeight={750}>Immutable model lifecycle</Typography><Typography variant="h3" fontWeight={760}>{item.model_name}</Typography><Typography color="text.secondary" mt={1}>{item.algorithm} · {item.feature_count} ordered features · outcome {item.outcome_column}</Typography></div><Chip label={item.status} color={item.status === 'LOCKED' ? 'success' : item.status === 'RETIRED' ? 'default' : item.status === 'REVIEWED' ? 'secondary' : 'warning'} /></Stack>
    <Alert severity="warning">Research model only. Review and lock freeze technical assets and decision provenance; they do not establish independent or clinical validity.</Alert>
    <Paper variant="outlined" sx={{ p: 3 }}><Typography variant="h5" fontWeight={720}>Lock readiness</Typography><Grid container spacing={1.5} mt={0.5}>{Object.entries(readiness.data.checks).map(([name, passed]) => <Grid item xs={12} sm={6} md={4} key={name}><Chip label={`${passed ? 'PASS' : 'BLOCKED'} · ${name.replaceAll('_', ' ')}`} color={passed ? 'success' : 'error'} variant={passed ? 'outlined' : 'filled'} /></Grid>)}</Grid>{readiness.data.blockers.length > 0 && <Alert severity="error" sx={{ mt: 2 }}>{readiness.data.blockers.join(' ')}</Alert>}{readiness.data.warnings.map((warning) => <Alert severity="warning" sx={{ mt: 1 }} key={warning}>{warning}</Alert>)}</Paper>
    <Stack direction={{ xs: 'column', sm: 'row' }} gap={1.5}>{item.status === 'CANDIDATE' && <Button variant="contained" color="secondary" startIcon={<VerifiedRoundedIcon />} onClick={() => setDecision('review')}>Complete technical review</Button>}{item.status === 'REVIEWED' && <Button variant="contained" color="secondary" startIcon={<LockRoundedIcon />} disabled={!readiness.data.ready} onClick={() => setDecision('lock')}>Lock immutable model</Button>}{item.status === 'LOCKED' && <Button variant="outlined" onClick={() => integrity.mutate()}>Verify asset integrity</Button>}{item.status === 'LOCKED' && <Button color="error" onClick={() => setDecision('retire')}>Retire model</Button>}<Button variant="outlined" disabled={clone.isPending} onClick={() => clone.mutate()}>Clone as new candidate</Button></Stack>
    {integrity.data && <Alert severity={integrity.data.valid ? 'success' : 'error'}>{integrity.data.valid ? 'Every locked asset and derived checksum matches.' : integrity.data.errors.join(' ')}</Alert>}
    {item.status === 'LOCKED' && <Paper variant="outlined" sx={{ p: 3 }}><Typography variant="h5" fontWeight={720}>Locked package</Typography><Typography variant="body2" color="text.secondary" mt={1}>Manifest {item.model_manifest_sha256}<br />Package {item.model_package_sha256}<br />Inference fixture {item.inference_test_status}</Typography><Stack direction="row" gap={2} mt={2}><Button component="a" href={modelManifestUrl(item.id)} startIcon={<DownloadRoundedIcon />}>ModelManifest</Button><Button component="a" href={modelPackageUrl(item.id)} startIcon={<DownloadRoundedIcon />}>Locked package</Button></Stack></Paper>}
    {(transition.isError || clone.isError || integrity.isError) && <ErrorState error={transition.error || clone.error || integrity.error} />}
    <Dialog open={decision !== null} onClose={() => setDecision(null)} fullWidth maxWidth="sm"><DialogTitle>{decision === 'review' ? 'Complete model review' : decision === 'lock' ? 'Lock immutable model' : 'Retire locked model'}</DialogTitle><DialogContent><Stack spacing={2} mt={1}><Alert severity="info">A scientist rationale is stored in the immutable decision and audit trail.</Alert><TextField required multiline minRows={3} label="Scientist rationale" value={rationale} onChange={(event) => setRationale(event.target.value)} /></Stack></DialogContent><DialogActions><Button onClick={() => setDecision(null)}>Cancel</Button><Button variant="contained" color={decision === 'retire' ? 'error' : 'secondary'} disabled={!rationale.trim() || transition.isPending} onClick={() => transition.mutate()}>Confirm {decision}</Button></DialogActions></Dialog>
  </Stack>
}
