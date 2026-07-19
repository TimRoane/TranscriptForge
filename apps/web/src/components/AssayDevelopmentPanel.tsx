import BiotechRoundedIcon from '@mui/icons-material/BiotechRounded'
import ArrowForwardRoundedIcon from '@mui/icons-material/ArrowForwardRounded'
import {
  Button,
  Card,
  CardActions,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'

import {
  createAssayProject,
  fetchProjectAssayDevelopment,
} from '../api/client'
import { ErrorState, LoadingState } from './ApiState'

export function AssayDevelopmentPanel({ projectId, projectName }: { projectId: string; projectName: string }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState(`${projectName} assay development`)
  const [purpose, setPurpose] = useState('')
  const [specimen, setSpecimen] = useState('')
  const [context, setContext] = useState('')
  const [output, setOutput] = useState('')
  const assay = useQuery({
    queryKey: ['project-assay-development', projectId],
    queryFn: ({ signal }) => fetchProjectAssayDevelopment(projectId, signal),
  })
  const create = useMutation({
    mutationFn: () => createAssayProject({
      project_id: projectId,
      name: name.trim(),
      proposed_purpose: purpose.trim() || undefined,
      specimen_type: specimen.trim() || undefined,
      biological_context: context.trim() || undefined,
      proposed_output: output.trim() || undefined,
      assay_version: 'development-unlocked',
    }),
    onSuccess: async () => {
      setOpen(false)
      await queryClient.invalidateQueries({ queryKey: ['project-assay-development', projectId] })
      await queryClient.invalidateQueries({ queryKey: ['assay-projects'] })
    },
  })

  if (assay.isPending) return <LoadingState label="Loading assay-development workspace…" />
  if (assay.isError) return <ErrorState error={assay.error} />

  return (
    <>
      <Card variant="outlined" sx={{ borderColor: 'secondary.light' }}>
        <CardContent>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <BiotechRoundedIcon color="secondary" />
            <div>
              <Typography variant="overline" color="secondary.main" fontWeight={750}>Question-first workspace</Typography>
              <Typography variant="h5" fontWeight={720}>Assay development</Typography>
            </div>
          </Stack>
          {assay.data ? (
            <Stack direction="row" spacing={1} mt={2} flexWrap="wrap" useFlexGap>
              <Chip label={assay.data.current_stage} color="secondary" />
              <Chip label={assay.data.readiness_status.replaceAll('_', ' ')} variant="outlined" />
            </Stack>
          ) : (
            <Typography color="text.secondary" mt={2}>
              Start from a scientific question, keep assumptions visible, and record each material scientist decision.
            </Typography>
          )}
        </CardContent>
        <CardActions>
          {assay.data ? (
            <Button component={RouterLink} to={`/assay-development/${assay.data.id}`} endIcon={<ArrowForwardRoundedIcon />}>
              Open guided workspace
            </Button>
          ) : (
            <Button variant="contained" color="secondary" onClick={() => setOpen(true)}>
              Start assay development
            </Button>
          )}
        </CardActions>
      </Card>

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Define the proposed assay-development problem</DialogTitle>
        <DialogContent>
          <Stack spacing={2} mt={1}>
            <Typography color="text.secondary">
              These fields establish context; TranscriptForge does not judge whether the proposed purpose is clinically appropriate.
            </Typography>
            <TextField label="Workspace name" required value={name} onChange={(event) => setName(event.target.value)} />
            <TextField label="Proposed purpose" multiline minRows={2} value={purpose} onChange={(event) => setPurpose(event.target.value)} helperText="What decision or research use is this work intended to inform?" />
            <TextField label="Specimen type" value={specimen} onChange={(event) => setSpecimen(event.target.value)} helperText="For example: FFPE tumor RNA" />
            <TextField label="Biological context" multiline minRows={2} value={context} onChange={(event) => setContext(event.target.value)} />
            <TextField label="Proposed output" value={output} onChange={(event) => setOutput(event.target.value)} helperText="For example: expression classifier score" />
            {create.isError && <ErrorState error={create.error} />}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="contained" color="secondary" disabled={!name.trim() || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? 'Creating…' : 'Create guided workspace'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  )
}
