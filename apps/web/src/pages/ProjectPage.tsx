import AddRoundedIcon from '@mui/icons-material/AddRounded'
import ArrowBackRoundedIcon from '@mui/icons-material/ArrowBackRounded'
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded'
import { Button, Link, Stack, Typography } from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom'

import { type CreateDatasetRequest, createDataset, deleteProject, fetchDatasets, fetchProject } from '../api/client'
import { ErrorState, LoadingState } from '../components/ApiState'
import { DeleteProjectDialog } from '../components/DeleteProjectDialog'
import { DatasetCard } from '../components/DatasetCard'
import { DatasetWizard } from '../components/DatasetWizard'
import { SignatureDefinitionPanel } from '../components/SignatureDefinitionPanel'

export function ProjectPage() {
  const { projectId = '' } = useParams()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [wizardOpen, setWizardOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const project = useQuery({ queryKey: ['project', projectId], queryFn: ({ signal }) => fetchProject(projectId, signal), enabled: !!projectId })
  const datasets = useQuery({ queryKey: ['datasets', projectId], queryFn: ({ signal }) => fetchDatasets(projectId, signal), enabled: !!projectId })
  const create = useMutation({
    mutationFn: (request: CreateDatasetRequest) => createDataset(projectId, request),
    onSuccess: async () => {
      setWizardOpen(false)
      await queryClient.invalidateQueries({ queryKey: ['datasets', projectId] })
    },
  })
  const remove = useMutation({
    mutationFn: () => deleteProject(projectId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['projects'] })
      navigate('/projects')
    },
  })

  if (project.isPending) return <LoadingState label="Loading project…" />
  if (project.isError) return <ErrorState error={project.error} />

  return (
    <Stack spacing={3}>
      <Link component={RouterLink} to="/projects" underline="hover" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, width: 'fit-content' }}>
        <ArrowBackRoundedIcon fontSize="small" /> Projects
      </Link>
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={2}>
        <div>
          <Typography variant="h3" fontWeight={750}>{project.data.name}</Typography>
          <Typography color="text.secondary" mt={1}>{project.data.description || 'No description provided.'}</Typography>
        </div>
        <Stack direction="row" spacing={1} sx={{ alignSelf: 'center' }}>
          <Button color="error" startIcon={<DeleteOutlineRoundedIcon />} onClick={() => setDeleteOpen(true)}>Delete project</Button>
          <Button variant="contained" startIcon={<AddRoundedIcon />} onClick={() => setWizardOpen(true)}>Add dataset</Button>
        </Stack>
      </Stack>
      <SignatureDefinitionPanel projectId={projectId} />
      <Typography variant="h5" fontWeight={700}>Datasets</Typography>
      {datasets.isPending && <LoadingState label="Loading datasets…" />}
      {datasets.isError && <ErrorState error={datasets.error} />}
      {datasets.data?.length === 0 && <Typography color="text.secondary">No datasets registered yet.</Typography>}
      {datasets.data?.map((dataset) => <DatasetCard dataset={dataset} key={dataset.id} />)}
      <DatasetWizard
        open={wizardOpen}
        pending={create.isPending}
        error={create.isError ? create.error.message : null}
        onClose={() => setWizardOpen(false)}
        onSubmit={(request) => create.mutate(request)}
      />
      <DeleteProjectDialog
        project={project.data}
        open={deleteOpen}
        pending={remove.isPending}
        error={remove.isError ? remove.error : null}
        onClose={() => {
          remove.reset()
          setDeleteOpen(false)
        }}
        onConfirm={() => remove.mutate()}
      />
    </Stack>
  )
}
