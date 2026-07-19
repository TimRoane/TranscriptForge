import CheckCircleRoundedIcon from '@mui/icons-material/CheckCircleRounded'
import ScienceRoundedIcon from '@mui/icons-material/ScienceRounded'
import {
  AppBar,
  Button,
  Chip,
  Container,
  CssBaseline,
  Stack,
  ThemeProvider,
  Toolbar,
  Typography,
  createTheme,
} from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { Link as RouterLink, Route, Routes } from 'react-router-dom'

import { fetchHealth } from './api/client'
import { DashboardPage } from './pages/DashboardPage'
import { ExternalValidationPage } from './pages/ExternalValidationPage'
import { AnalysisPage } from './pages/AnalysisPage'
import { AssayDevelopmentListPage } from './pages/AssayDevelopmentListPage'
import { AssayDevelopmentPage } from './pages/AssayDevelopmentPage'
import { HomePage } from './pages/HomePage'
import { ExperimentDesignerPage } from './pages/ExperimentDesignerPage'
import { ExperimentPage } from './pages/ExperimentPage'
import { GuidedAnalysisLauncherPage } from './pages/GuidedAnalysisLauncherPage'
import { ModelPage } from './pages/ModelPage'
import { ProjectPage } from './pages/ProjectPage'
import { PreparedDatasetPage } from './pages/PreparedDatasetPage'
import { StudyDesignerPage } from './pages/StudyDesignerPage'
import { StudyPage } from './pages/StudyPage'

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#155e75' },
    secondary: { main: '#7c3aed' },
    background: { default: '#f4f7f8' },
  },
  typography: {
    fontFamily: 'Inter, system-ui, sans-serif',
    h1: { fontWeight: 750, letterSpacing: '-0.04em' },
  },
  shape: { borderRadius: 12 },
})

export function App() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: ({ signal }) => fetchHealth(signal),
    retry: 1,
  })

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AppBar position="static" elevation={0}>
        <Toolbar>
          <Stack component={RouterLink} to="/" direction="row" alignItems="center" color="inherit" sx={{ textDecoration: 'none', flexGrow: 1 }}>
            <ScienceRoundedIcon sx={{ mr: 1.5 }} />
            <Typography variant="h6" component="div" fontWeight={700}>TranscriptForge</Typography>
          </Stack>
          <Button component={RouterLink} to="/" color="inherit" sx={{ display: { xs: 'none', sm: 'inline-flex' }, mr: 0.5 }}>Overview</Button>
          <Button component={RouterLink} to="/projects" color="inherit" sx={{ mr: 1.5 }}>Projects</Button>
          <Button component={RouterLink} to="/assay-development" color="inherit" sx={{ display: { xs: 'none', md: 'inline-flex' }, mr: 1.5 }}>Assay Development</Button>
          {health.data && <CheckCircleRoundedIcon aria-label="API connected" sx={{ mr: 1, fontSize: 18 }} />}
          {health.data?.deployment_mode === 'single_user_local' && (
            <Chip label="Local single-user" size="small" sx={{ mr: 1, display: { xs: 'none', md: 'inline-flex' } }} />
          )}
          <Chip label="Research use only" color="secondary" size="small" />
        </Toolbar>
      </AppBar>
      <Container maxWidth="lg" sx={{ py: { xs: 4, md: 7 } }}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/projects" element={<DashboardPage />} />
          <Route path="/projects/:projectId" element={<ProjectPage />} />
          <Route path="/assay-development" element={<AssayDevelopmentListPage />} />
          <Route path="/assay-development/:assayProjectId" element={<AssayDevelopmentPage />} />
          <Route path="/assay-development/:assayProjectId/experiments/new" element={<ExperimentDesignerPage />} />
          <Route path="/assay-development/:assayProjectId/questions/:questionId/analysis" element={<GuidedAnalysisLauncherPage />} />
          <Route path="/experiments/:experimentId" element={<ExperimentPage />} />
          <Route path="/assay-development/:assayProjectId/studies/new" element={<StudyDesignerPage />} />
          <Route path="/studies/:studyId" element={<StudyPage />} />
          <Route path="/prepared-datasets/:preparedDatasetId" element={<PreparedDatasetPage />} />
          <Route path="/analyses/:analysisId" element={<AnalysisPage />} />
          <Route path="/models/:modelId" element={<ModelPage />} />
          <Route path="/classifier-external-validations/:validationId" element={<ExternalValidationPage />} />
          <Route path="*" element={<Typography>Page not found.</Typography>} />
        </Routes>
      </Container>
    </ThemeProvider>
  )
}
