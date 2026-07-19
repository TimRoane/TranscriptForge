import {
  Checkbox,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'

import type { StudyAssignment } from '../api/client'

interface Props {
  assignments: StudyAssignment[]
  editable: boolean
  template?: 'precision' | 'input_limit' | 'paired_bridge' | 'robustness'
  onChange?: (assignments: StudyAssignment[]) => void
}

const fields = [
  ['biological_sample_id', 'Biological sample'],
  ['replicate_id', 'Replicate'],
  ['operator', 'Operator'],
  ['run', 'Run'],
  ['reagent_lot', 'Reagent lot'],
  ['instrument', 'Instrument'],
  ['day', 'Day'],
  ['site', 'Site'],
] as const

export function StudyAssignmentTable({ assignments, editable, template = 'precision', onChange }: Props) {
  const update = (index: number, patch: Partial<StudyAssignment>) => {
    onChange?.(assignments.map((row, rowIndex) => rowIndex === index ? { ...row, ...patch } : row))
  }

  if (!assignments.length) {
    return <Typography color="text.secondary">Select a validation Expression Bundle to map its measurements.</Typography>
  }

  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small" sx={{ minWidth: 1420 }}>
        <TableHead>
          <TableRow>
            <TableCell>Include</TableCell>
            <TableCell>Measurement ID</TableCell>
            {template === 'precision' ? fields.map(([, label]) => <TableCell key={label}>{label}</TableCell>) : template === 'input_limit' ? <><TableCell>Biological sample</TableCell><TableCell>Input / quality level</TableCell><TableCell>Quality metric</TableCell><TableCell>Run</TableCell><TableCell>QC failure</TableCell></> : <><TableCell>Biological sample</TableCell><TableCell>Condition</TableCell>{template === 'robustness' && <TableCell>Challenge type</TableCell>}<TableCell>Run</TableCell><TableCell>Subgroup</TableCell>{template === 'robustness' && <TableCell>QC failure</TableCell>}</>}
            <TableCell>Exclusion reason</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {assignments.map((row, index) => (
            <TableRow key={row.measurement_id} sx={{ opacity: row.include ? 1 : 0.65 }}>
              <TableCell>
                <Checkbox
                  checked={row.include}
                  disabled={!editable}
                  inputProps={{ 'aria-label': `Include ${row.measurement_id}` }}
                  onChange={(event) => update(index, {
                    include: event.target.checked,
                    exclusion_reason: event.target.checked ? null : row.exclusion_reason,
                  })}
                />
              </TableCell>
              <TableCell><Typography fontFamily="monospace" variant="body2">{row.measurement_id}</Typography></TableCell>
              {template === 'precision' ? fields.map(([field]) => {
                const required = ['biological_sample_id', 'replicate_id', 'operator', 'run', 'reagent_lot'].includes(field)
                return (
                  <TableCell key={field}>
                    <TextField
                      size="small"
                      value={row[field] || ''}
                      disabled={!editable || !row.include}
                      error={row.include && required && !row[field]}
                      required={required}
                      onChange={(event) => update(index, { [field]: event.target.value })}
                      sx={{ minWidth: 130 }}
                    />
                  </TableCell>
                )
              }) : template === 'input_limit' ? <>
                <TableCell><TextField size="small" required value={row.biological_sample_id} disabled={!editable || !row.include} onChange={(event) => update(index, { biological_sample_id: event.target.value })} /></TableCell>
                <TableCell><TextField size="small" required type="number" value={row.input_level ?? ''} disabled={!editable || !row.include} onChange={(event) => update(index, { input_level: event.target.value === '' ? null : Number(event.target.value) })} /></TableCell>
                <TableCell><TextField size="small" type="number" value={row.quality_metric ?? ''} disabled={!editable || !row.include} onChange={(event) => update(index, { quality_metric: event.target.value === '' ? null : Number(event.target.value) })} /></TableCell>
                <TableCell><TextField size="small" required value={row.run || ''} disabled={!editable || !row.include} onChange={(event) => update(index, { run: event.target.value || null })} /></TableCell>
                <TableCell><Checkbox checked={row.qc_failure} disabled={!editable || !row.include} onChange={(event) => update(index, { qc_failure: event.target.checked })} /></TableCell>
              </> : <>
                <TableCell><TextField size="small" required value={row.biological_sample_id} disabled={!editable || !row.include} onChange={(event) => update(index, { biological_sample_id: event.target.value })} /></TableCell>
                <TableCell><TextField size="small" required value={row.condition || ''} disabled={!editable || !row.include} onChange={(event) => update(index, { condition: event.target.value || null })} /></TableCell>
                {template === 'robustness' && <TableCell><TextField size="small" required value={row.challenge_type || ''} disabled={!editable || !row.include} onChange={(event) => update(index, { challenge_type: event.target.value || null })} /></TableCell>}
                <TableCell><TextField size="small" required value={row.run || ''} disabled={!editable || !row.include} onChange={(event) => update(index, { run: event.target.value || null })} /></TableCell>
                <TableCell><TextField size="small" value={row.subgroup || ''} disabled={!editable || !row.include} onChange={(event) => update(index, { subgroup: event.target.value || null })} /></TableCell>
                {template === 'robustness' && <TableCell><Checkbox checked={row.qc_failure} disabled={!editable || !row.include} onChange={(event) => update(index, { qc_failure: event.target.checked })} /></TableCell>}
              </>}
              <TableCell>
                <TextField
                  size="small"
                  value={row.exclusion_reason || ''}
                  disabled={!editable || row.include}
                  error={!row.include && !row.exclusion_reason}
                  required={!row.include}
                  onChange={(event) => update(index, { exclusion_reason: event.target.value || null })}
                  sx={{ minWidth: 180 }}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  )
}
