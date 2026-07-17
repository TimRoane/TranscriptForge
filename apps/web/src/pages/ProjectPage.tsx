import AddRoundedIcon from '@mui/icons-material/AddRounded'
import ArrowBackRoundedIcon from '@mui/icons-material/ArrowBackRounded'
import { Button, Link, Stack, Typography } from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link as RouterLink, useParams } from 'react-router-dom'

import { type CreateDatasetRequest, createDataset, fetchDatasets, fetchProject } from '../api/client'
import { ErrorState, LoadingState } from '../components/ApiState'
import { DatasetCard } from '../components/DatasetCard'
import { DatasetWizard } from '../components/DatasetWizard'
import { SignatureDefinitionPanel } from '../components/SignatureDefinitionPanel'

export function ProjectPage() {
  const { projectId = '' } = useParams()
  const queryClient = useQueryClient()
  const [wizardOpen, setWizardOpen] = useState(false)
  const project = useQuery({ queryKey: ['project', projectId], queryFn: ({ signal }) => fetchProject(projectId, signal), enabled: !!projectId })
  const datasets = useQuery({ queryKey: ['datasets', projectId], queryFn: ({ signal }) => fetchDatasets(projectId, signal), enabled: !!projectId })
  const create = useMutation({
    mutationFn: (request: CreateDatasetRequest) => createDataset(projectId, request),
    onSuccess: async () => {
      setWizardOpen(false)
      await queryClient.invalidateQueries({ queryKey: ['datasets', projectId] })
    },
  })

  if (project.isPending) return <LoadingState label="Loading project…" />
  if (project.isError) return <ErrorState error={project.error} />

  return (
    <Stack spacing={3}>
      <Link component={RouterLink} to="/" underline="hover" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, width: 'fit-content' }}>
        <ArrowBackRoundedIcon fontSize="small" /> Projects
      </Link>
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={2}>
        <div>
          <Typography variant="h3" fontWeight={750}>{project.data.name}</Typography>
          <Typography color="text.secondary" mt={1}>{project.data.description || 'No description provided.'}</Typography>
        </div>
        <Button variant="contained" startIcon={<AddRoundedIcon />} onClick={() => setWizardOpen(true)} sx={{ alignSelf: 'center' }}>Add dataset</Button>
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
    </Stack>
  )
}
