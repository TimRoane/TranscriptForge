import ArrowForwardRoundedIcon from '@mui/icons-material/ArrowForwardRounded'
import BiotechRoundedIcon from '@mui/icons-material/BiotechRounded'
import DatasetRoundedIcon from '@mui/icons-material/DatasetRounded'
import HubRoundedIcon from '@mui/icons-material/HubRounded'
import VerifiedRoundedIcon from '@mui/icons-material/VerifiedRounded'
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  Paper,
  Stack,
  Typography,
} from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { Link as RouterLink } from 'react-router-dom'

import { fetchProjects } from '../api/client'
import { ErrorState } from '../components/ApiState'

const capabilities = [
  {
    icon: <DatasetRoundedIcon color="primary" />,
    title: 'Multiple input paths',
    description: 'Count and expression matrices, paired or single-end FASTQ, and Affymetrix CEL files converge on one analysis-ready contract.',
  },
  {
    icon: <BiotechRoundedIcon color="primary" />,
    title: 'Scientific workflows',
    description: 'QC, dimension reduction, differential expression, enrichment, and signature scoring execute in versioned R and Python runtimes.',
  },
  {
    icon: <VerifiedRoundedIcon color="primary" />,
    title: 'Evidence preserved',
    description: 'Every run retains checksums, frozen parameters, software versions, reports, plots, tables, and workflow provenance.',
  },
]

const workflow = [
  ['01', 'Register data', 'Create a project and declare the assay, source format, reference, and sample metadata.'],
  ['02', 'Validate and prepare', 'Check scientific inputs before building an immutable Expression Bundle.'],
  ['03', 'Explore and compare', 'Inspect QC, sample structure, model design, contrasts, pathways, and signatures.'],
  ['04', 'Review the evidence', 'Download complete results, reports, contracts, checksums, and execution provenance.'],
]

export function HomePage() {
  const projects = useQuery({
    queryKey: ['projects'],
    queryFn: ({ signal }) => fetchProjects(signal),
  })
  const recentProjects = projects.data?.slice(0, 3) ?? []

  return (
    <Stack spacing={{ xs: 6, md: 8 }}>
      <Paper
        elevation={0}
        sx={{
          position: 'relative',
          overflow: 'hidden',
          px: { xs: 3, md: 7 },
          py: { xs: 5, md: 8 },
          color: 'common.white',
          background: 'linear-gradient(135deg, #0f4c5c 0%, #155e75 58%, #4c1d95 135%)',
        }}
      >
        <Box
          sx={{
            position: 'absolute',
            width: 360,
            height: 360,
            borderRadius: '50%',
            bgcolor: 'rgba(255,255,255,0.08)',
            right: -100,
            top: -150,
          }}
        />
        <Stack spacing={3} sx={{ position: 'relative', maxWidth: 820 }}>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Chip label="Human transcriptomics" size="small" sx={{ color: 'white', bgcolor: 'rgba(255,255,255,0.16)' }} />
            <Chip label="Workflow-backed" size="small" sx={{ color: 'white', bgcolor: 'rgba(255,255,255,0.16)' }} />
            <Chip label="Reproducible outputs" size="small" sx={{ color: 'white', bgcolor: 'rgba(255,255,255,0.16)' }} />
          </Stack>
          <Typography variant="h2" component="h1" fontWeight={800} sx={{ fontSize: { xs: '2.6rem', md: '4.4rem' }, lineHeight: 1.02 }}>
            From expression data to auditable results.
          </Typography>
          <Typography variant="h6" sx={{ maxWidth: 700, color: 'rgba(255,255,255,0.82)', fontWeight: 400, lineHeight: 1.55 }}>
            TranscriptForge brings RNA-seq and microarray preparation, quality control,
            statistical analysis, and reproducible reporting into one research workspace.
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} pt={1}>
            <Button
              component={RouterLink}
              to="/projects"
              variant="contained"
              color="inherit"
              endIcon={<ArrowForwardRoundedIcon />}
              sx={{ color: 'primary.dark', bgcolor: 'common.white', '&:hover': { bgcolor: 'grey.100' } }}
            >
              Open workspace
            </Button>
            <Button
              component={RouterLink}
              to="/projects?new=1"
              variant="outlined"
              sx={{ color: 'common.white', borderColor: 'rgba(255,255,255,0.6)', '&:hover': { borderColor: 'common.white', bgcolor: 'rgba(255,255,255,0.08)' } }}
            >
              Start a project
            </Button>
          </Stack>
        </Stack>
      </Paper>

      <Box>
        <Typography variant="overline" color="secondary.main" fontWeight={750}>One reproducible workspace</Typography>
        <Typography variant="h4" fontWeight={750} mt={0.5}>Built around the scientific record</Typography>
        <Grid container spacing={2.5} mt={1}>
          {capabilities.map((capability) => (
            <Grid item xs={12} md={4} key={capability.title}>
              <Card variant="outlined" sx={{ height: '100%' }}>
                <CardContent sx={{ p: 3 }}>
                  {capability.icon}
                  <Typography variant="h6" fontWeight={700} mt={2}>{capability.title}</Typography>
                  <Typography color="text.secondary" mt={1} lineHeight={1.65}>{capability.description}</Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Box>

      <Paper variant="outlined" sx={{ p: { xs: 3, md: 4 } }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <HubRoundedIcon color="secondary" />
          <Typography variant="h4" fontWeight={750}>A clear path through the analysis</Typography>
        </Stack>
        <Grid container spacing={3} mt={0.5}>
          {workflow.map(([number, title, description]) => (
            <Grid item xs={12} sm={6} md={3} key={number}>
              <Typography variant="overline" color="secondary.main" fontWeight={800}>{number}</Typography>
              <Typography variant="h6" fontWeight={700}>{title}</Typography>
              <Typography color="text.secondary" mt={0.75} lineHeight={1.55}>{description}</Typography>
            </Grid>
          ))}
        </Grid>
      </Paper>

      <Box>
        <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'flex-end' }} gap={2}>
          <div>
            <Typography variant="overline" color="primary" fontWeight={750}>Continue your work</Typography>
            <Typography variant="h4" fontWeight={750}>Recent projects</Typography>
          </div>
          <Button component={RouterLink} to="/projects" endIcon={<ArrowForwardRoundedIcon />}>
            View all projects
          </Button>
        </Stack>
        {projects.isError && <Box mt={2}><ErrorState error={projects.error} /></Box>}
        {!projects.isPending && !projects.isError && recentProjects.length === 0 && (
          <Paper variant="outlined" sx={{ p: 3, mt: 2 }}>
            <Typography>No projects yet. Start a project to register your first dataset.</Typography>
          </Paper>
        )}
        <Grid container spacing={2} mt={0.5}>
          {recentProjects.map((project) => (
            <Grid item xs={12} md={4} key={project.id}>
              <Card variant="outlined" sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                <CardContent sx={{ flexGrow: 1 }}>
                  <Typography variant="h6" fontWeight={700}>{project.name}</Typography>
                  <Typography color="text.secondary" mt={1}>{project.description || 'No description provided.'}</Typography>
                </CardContent>
                <Box px={2} pb={2}>
                  <Button component={RouterLink} to={`/projects/${project.id}`} endIcon={<ArrowForwardRoundedIcon />}>
                    Open project
                  </Button>
                </Box>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Box>
    </Stack>
  )
}
