import { Alert, CircularProgress, Stack, Typography } from '@mui/material'

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <Stack direction="row" spacing={1.5} alignItems="center" py={2}>
      <CircularProgress size={20} />
      <Typography>{label}</Typography>
    </Stack>
  )
}

export function ErrorState({ error }: { error: unknown }) {
  return (
    <Alert severity="error">
      {error instanceof Error ? error.message : 'The request could not be completed.'}
    </Alert>
  )
}
