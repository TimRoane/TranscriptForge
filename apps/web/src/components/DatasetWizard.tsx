import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Step,
  StepLabel,
  Stepper,
  TextField,
} from '@mui/material'
import { useState } from 'react'

import type { CreateDatasetRequest, DatasetModality, DatasetSourceKind } from '../api/client'

const compatibleSources: Record<DatasetModality, DatasetSourceKind[]> = {
  bulk_rnaseq: ['count_matrix', 'fastq', 'salmon_quant'],
  microarray: ['normalized_matrix', 'affymetrix_cel'],
  generic_expression: ['normalized_matrix'],
}

interface DatasetWizardProps {
  open: boolean
  pending: boolean
  error: string | null
  onClose: () => void
  onSubmit: (request: CreateDatasetRequest) => void
}

export function DatasetWizard({ open, pending, error, onClose, onSubmit }: DatasetWizardProps) {
  const [step, setStep] = useState(0)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [modality, setModality] = useState<DatasetModality>('bulk_rnaseq')
  const [sourceKind, setSourceKind] = useState<DatasetSourceKind>('count_matrix')
  const [annotationRelease, setAnnotationRelease] = useState('')

  const close = () => {
    setStep(0)
    onClose()
  }

  const selectModality = (next: DatasetModality) => {
    setModality(next)
    setSourceKind(compatibleSources[next][0])
  }

  const selectSourceKind = (next: DatasetSourceKind) => {
    setSourceKind(next)
    if (next === 'fastq') setAnnotationRelease('GENCODE 50')
    if (next === 'affymetrix_cel') {
      setAnnotationRelease('hugene10sttranscriptcluster.db 8.8.0')
    }
  }

  return (
    <Dialog open={open} onClose={pending ? undefined : close} fullWidth maxWidth="sm">
      <DialogTitle>Register a dataset</DialogTitle>
      <DialogContent>
        <Stepper activeStep={step} sx={{ py: 2 }}>
          {['Describe', 'Source', 'Identifiers'].map((label) => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {step === 0 && (
          <Stack spacing={2} mt={1}>
            <TextField
              label="Dataset name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              autoFocus
            />
            <TextField
              label="Description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              multiline
              minRows={3}
            />
          </Stack>
        )}
        {step === 1 && (
          <Stack spacing={2} mt={1}>
            <FormControl>
              <InputLabel id="modality-label">Modality</InputLabel>
              <Select
                labelId="modality-label"
                label="Modality"
                value={modality}
                onChange={(event) => selectModality(event.target.value as DatasetModality)}
              >
                <MenuItem value="bulk_rnaseq">Bulk RNA-seq</MenuItem>
                <MenuItem value="microarray">Microarray</MenuItem>
                <MenuItem value="generic_expression">Generic expression</MenuItem>
              </Select>
            </FormControl>
            <FormControl>
              <InputLabel id="source-label">Source type</InputLabel>
              <Select
                labelId="source-label"
                label="Source type"
                value={sourceKind}
                onChange={(event) => selectSourceKind(event.target.value as DatasetSourceKind)}
              >
                {compatibleSources[modality].map((source) => (
                  <MenuItem value={source} key={source}>{source.replaceAll('_', ' ')}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
        )}
        {step === 2 && (
          <Stack spacing={2} mt={1}>
            <TextField label="Organism" value="Homo sapiens" disabled />
            <TextField label="Genome build" value="GRCh38" disabled />
            <TextField
              label="Annotation release"
              placeholder={
                sourceKind === 'fastq'
                  ? 'GENCODE 50 (required)'
                  : sourceKind === 'affymetrix_cel'
                    ? 'Pinned by the selected platform adapter'
                    : 'For example, GENCODE 50'
              }
              value={annotationRelease}
              onChange={(event) => setAnnotationRelease(event.target.value)}
            />
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={close} disabled={pending}>Cancel</Button>
        {step > 0 && <Button onClick={() => setStep(step - 1)} disabled={pending}>Back</Button>}
        {step < 2 ? (
          <Button variant="contained" onClick={() => setStep(step + 1)} disabled={step === 0 && !name.trim()}>
            Continue
          </Button>
        ) : (
          <Button
            variant="contained"
            disabled={pending}
            onClick={() => onSubmit({
              name: name.trim(),
              description: description.trim() || undefined,
              modality,
              source_kind: sourceKind,
              genome_build: 'GRCh38',
              annotation_release: annotationRelease.trim() || undefined,
            })}
          >
            {pending ? 'Creating…' : 'Create dataset'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  )
}
