import AddRoundedIcon from '@mui/icons-material/AddRounded'
import ArrowForwardRoundedIcon from '@mui/icons-material/ArrowForwardRounded'
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded'
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
import { Link as RouterLink, useNavigate, useSearchParams } from 'react-router-dom'

import { createProject, deleteProject, fetchProjects, type Project } from '../api/client'
import { ErrorState, LoadingState } from '../components/ApiState'
import { DeleteProjectDialog } from '../components/DeleteProjectDialog'

export function DashboardPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [dialogOpen, setDialogOpen] = useState(searchParams.get('new') === '1')
  const [projectToDelete, setProjectToDelete] = useState<Project | null>(null)
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
  const remove = useMutation({
    mutationFn: (project: Project) => deleteProject(project.id),
    onSuccess: async () => {
      setProjectToDelete(null)
      await queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })

  const closeCreateDialog = () => {
    setDialogOpen(false)
    if (searchParams.has('new')) setSearchParams({}, { replace: true })
  }

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
              <CardActions sx={{ justifyContent: 'space-between' }}>
                <Button component={RouterLink} to={`/projects/${project.id}`} endIcon={<ArrowForwardRoundedIcon />}>Open project</Button>
                <Button
                  color="error"
                  startIcon={<DeleteOutlineRoundedIcon />}
                  onClick={() => {
                    remove.reset()
                    setProjectToDelete(project)
                  }}
                  aria-label={`Delete ${project.name}`}
                >
                  Delete
                </Button>
              </CardActions>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Dialog open={dialogOpen} onClose={closeCreateDialog} fullWidth maxWidth="sm">
        <DialogTitle>Create a project</DialogTitle>
        <DialogContent><Stack spacing={2} mt={1}>
          <TextField label="Project name" required autoFocus value={name} onChange={(event) => setName(event.target.value)} />
          <TextField label="Description" multiline minRows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
          {create.isError && <ErrorState error={create.error} />}
        </Stack></DialogContent>
        <DialogActions>
          <Button onClick={closeCreateDialog}>Cancel</Button>
          <Button variant="contained" disabled={!name.trim() || create.isPending} onClick={() => create.mutate({ name: name.trim(), description: description.trim() || undefined })}>
            {create.isPending ? 'Creating…' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>
      <DeleteProjectDialog
        project={projectToDelete}
        open={projectToDelete !== null}
        pending={remove.isPending}
        error={remove.isError ? remove.error : null}
        onClose={() => {
          remove.reset()
          setProjectToDelete(null)
        }}
        onConfirm={() => {
          if (projectToDelete) remove.mutate(projectToDelete)
        }}
      />
    </Stack>
  )
}
