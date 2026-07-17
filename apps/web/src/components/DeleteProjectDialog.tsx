import WarningAmberRoundedIcon from '@mui/icons-material/WarningAmberRounded'
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useState } from 'react'

import type { Project } from '../api/client'
import { ErrorState } from './ApiState'

interface DeleteProjectDialogProps {
  project: Project | null
  open: boolean
  pending: boolean
  error: Error | null
  onClose: () => void
  onConfirm: () => void
}

export function DeleteProjectDialog({
  project,
  open,
  pending,
  error,
  onClose,
  onConfirm,
}: DeleteProjectDialogProps) {
  const [confirmation, setConfirmation] = useState('')

  useEffect(() => {
    if (!open) setConfirmation('')
  }, [open])

  const matches = project !== null && confirmation === project.name

  return (
    <Dialog open={open} onClose={pending ? undefined : onClose} fullWidth maxWidth="sm">
      <DialogTitle>Delete project?</DialogTitle>
      <DialogContent>
        <Stack spacing={2.5} mt={0.5}>
          <Alert severity="warning" icon={<WarningAmberRoundedIcon />}>
            This deletes the project record and its related datasets, analyses, runs, and indexed
            artifacts. Immutable stored files may remain until the retention cleanup policy runs.
          </Alert>
          <Typography>
            This action cannot be undone. Type <strong>{project?.name}</strong> to confirm.
          </Typography>
          <TextField
            label="Project name"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
            autoComplete="off"
            autoFocus
            disabled={pending}
          />
          {error && <ErrorState error={error} />}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={pending}>Cancel</Button>
        <Button color="error" variant="contained" disabled={!matches || pending} onClick={onConfirm}>
          {pending ? 'Deleting…' : 'Delete project'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
