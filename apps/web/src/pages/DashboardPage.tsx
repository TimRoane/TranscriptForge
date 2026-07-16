import AddRoundedIcon from '@mui/icons-material/AddRounded'
import ArrowForwardRoundedIcon from '@mui/icons-material/ArrowForwardRounded'
import {
  Button,
  Card,
  CardActions,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link as RouterLink, useNavigate } from 'react-router-dom'

import { createProject, fetchProjects } from '../api/client'
import { ErrorState, LoadingState } from '../components/ApiState'

export function DashboardPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const projects = useQuery({ queryKey: ['projects'], queryFn: ({ signal }) => fetchProjects(signal) })
  const create = useMutation({
    mutationFn: createProject,
    onSuccess: async (project) => {
      await queryClient.invalidateQueries({ queryKey: ['projects'] })
      navigate(`/projects/${project.id}`)
    },
  })

  return (
    <Stack spacing={4}>
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={2}>
        <div>
          <Typography variant="overline" color="primary" fontWeight={700}>Workspace</Typography>
          <Typography variant="h3" fontWeight={750}>Projects</Typography>
          <Typography color="text.secondary" mt={1}>Organize immutable datasets and reproducible analyses.</Typography>
        </div>
        <Button variant="contained" startIcon={<AddRoundedIcon />} onClick={() => setDialogOpen(true)} sx={{ alignSelf: 'center' }}>
          New project
        </Button>
      </Stack>

      {projects.isPending && <LoadingState label="Loading projects…" />}
      {projects.isError && <ErrorState error={projects.error} />}
      {projects.data?.length === 0 && (
        <Card variant="outlined"><CardContent><Typography>No projects yet. Create one to register your first dataset.</Typography></CardContent></Card>
      )}
      <Grid container spacing={2}>
        {projects.data?.map((project) => (
          <Grid item key={project.id} xs={12} md={6}>
            <Card variant="outlined" sx={{ height: '100%' }}>
              <CardContent>
                <Typography variant="h6">{project.name}</Typography>
                <Typography color="text.secondary" mt={1}>{project.description || 'No description provided.'}</Typography>
              </CardContent>
              <CardActions>
                <Button component={RouterLink} to={`/projects/${project.id}`} endIcon={<ArrowForwardRoundedIcon />}>Open project</Button>
              </CardActions>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Create a project</DialogTitle>
        <DialogContent><Stack spacing={2} mt={1}>
          <TextField label="Project name" required autoFocus value={name} onChange={(event) => setName(event.target.value)} />
          <TextField label="Description" multiline minRows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
          {create.isError && <ErrorState error={create.error} />}
        </Stack></DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={!name.trim() || create.isPending} onClick={() => create.mutate({ name: name.trim(), description: description.trim() || undefined })}>
            {create.isPending ? 'Creating…' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
