import ArrowForwardRoundedIcon from '@mui/icons-material/ArrowForwardRounded'
import BiotechRoundedIcon from '@mui/icons-material/BiotechRounded'
import { Button, Card, CardActions, CardContent, Chip, Grid, Stack, Typography } from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { Link as RouterLink } from 'react-router-dom'

import { fetchAssayProjects } from '../api/client'
import { ErrorState, LoadingState } from '../components/ApiState'

export function AssayDevelopmentListPage() {
  const projects = useQuery({ queryKey: ['assay-projects'], queryFn: ({ signal }) => fetchAssayProjects(signal) })
  return (
    <Stack spacing={4}>
      <div>
        <Typography variant="overline" color="secondary.main" fontWeight={750}>Guided evidence lifecycle</Typography>
        <Typography variant="h3" fontWeight={760}>Assay development</Typography>
        <Typography color="text.secondary" mt={1} maxWidth={780}>
          Begin with the scientific decision, inspect deterministic readiness rules, and preserve recommendations and scientist choices as evidence.
        </Typography>
      </div>
      {projects.isPending && <LoadingState label="Loading assay-development projects…" />}
      {projects.isError && <ErrorState error={projects.error} />}
      {projects.data?.length === 0 && (
        <Card variant="outlined"><CardContent>
          <BiotechRoundedIcon color="secondary" />
          <Typography variant="h6" mt={1}>No guided workspaces yet</Typography>
          <Typography color="text.secondary" mt={1}>Open a base project and select Start assay development.</Typography>
          <Button component={RouterLink} to="/projects" sx={{ mt: 2 }}>Open projects</Button>
        </CardContent></Card>
      )}
      <Grid container spacing={2}>
        {projects.data?.map((project) => (
          <Grid item xs={12} md={6} key={project.id}>
            <Card variant="outlined" sx={{ height: '100%' }}>
              <CardContent>
                <Typography variant="h6" fontWeight={720}>{project.name}</Typography>
                <Typography color="text.secondary" mt={1}>{project.proposed_purpose || 'Proposed purpose still needs to be recorded.'}</Typography>
                <Stack direction="row" spacing={1} mt={2} flexWrap="wrap" useFlexGap>
                  <Chip label={project.current_stage} color="secondary" size="small" />
                  <Chip label={project.readiness_status.replaceAll('_', ' ')} variant="outlined" size="small" />
                </Stack>
              </CardContent>
              <CardActions><Button component={RouterLink} to={`/assay-development/${project.id}`} endIcon={<ArrowForwardRoundedIcon />}>Open workspace</Button></CardActions>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Stack>
  )
}
