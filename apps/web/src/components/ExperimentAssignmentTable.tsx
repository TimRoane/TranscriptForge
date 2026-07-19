import {
  Checkbox,
  FormControlLabel,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'

import type { ExperimentAssignment } from '../api/client'

interface Props {
  assignments: ExperimentAssignment[]
  editable: boolean
  template?: 'technical_feasibility' | 'input_degradation' | 'paired_condition' | 'multifactor'
  onChange?: (assignments: ExperimentAssignment[]) => void
}

export function ExperimentAssignmentTable({ assignments, editable, template = 'input_degradation', onChange }: Props) {
  const update = (index: number, values: Partial<ExperimentAssignment>) => {
    onChange?.(assignments.map((item, itemIndex) => itemIndex === index ? { ...item, ...values } : item))
  }
  return (
    <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 520 }}>
      <Table stickyHeader size="small" aria-label="Experiment measurement assignments">
        <TableHead><TableRow>
          <TableCell>Include</TableCell><TableCell>Measurement</TableCell><TableCell>Biological sample</TableCell>
          {template === 'technical_feasibility'
            ? <><TableCell>Specimen group</TableCell><TableCell>Input (ng)</TableCell><TableCell>DV200</TableCell><TableCell>Run</TableCell><TableCell>Technical failure</TableCell></>
            : template === 'input_degradation'
            ? <><TableCell>Input (ng)</TableCell><TableCell>DV200</TableCell><TableCell>Sequencing run</TableCell></>
            : template === 'multifactor'
              ? <><TableCell>Extraction method</TableCell><TableCell>Input (ng)</TableCell><TableCell>Run</TableCell></>
              : <><TableCell>Condition</TableCell><TableCell>Quality metric</TableCell><TableCell>Run</TableCell></>}
          <TableCell>Operator</TableCell><TableCell>Reagent lot</TableCell><TableCell>Order</TableCell>
          <TableCell>Exclusion reason</TableCell>
        </TableRow></TableHead>
        <TableBody>{assignments.map((item, index) => <TableRow key={item.measurement_id}>
          <TableCell>
            {editable ? <Checkbox checked={item.include} onChange={(event) => update(index, { include: event.target.checked, exclusion_reason: event.target.checked ? null : item.exclusion_reason })} inputProps={{ 'aria-label': `Include ${item.measurement_id}` }} /> : <FormControlLabel control={<Checkbox checked={item.include} disabled />} label="" />}
          </TableCell>
          <TableCell><Typography variant="body2" fontFamily="monospace">{item.measurement_id}</Typography></TableCell>
          <TableCell><TextField size="small" required value={item.biological_sample_id} disabled={!editable} onChange={(event) => update(index, { biological_sample_id: event.target.value, pair_id: event.target.value })} inputProps={{ 'aria-label': `Biological sample ${item.measurement_id}` }} /></TableCell>
          {template === 'technical_feasibility' ? <>
            <TableCell><TextField size="small" value={item.specimen_group || ''} disabled={!editable} onChange={(event) => update(index, { specimen_group: event.target.value || null })} inputProps={{ 'aria-label': `Specimen group ${item.measurement_id}` }} /></TableCell>
            <TableCell><TextField size="small" type="number" value={item.input_ng || ''} disabled={!editable} onChange={(event) => update(index, { input_ng: Number(event.target.value) || null })} inputProps={{ min: 0, step: 'any', 'aria-label': `Input ng ${item.measurement_id}` }} /></TableCell>
            <TableCell><TextField size="small" type="number" value={item.dv200 ?? ''} disabled={!editable} onChange={(event) => update(index, { dv200: event.target.value === '' ? null : Number(event.target.value) })} inputProps={{ min: 0, max: 100, step: 'any', 'aria-label': `DV200 ${item.measurement_id}` }} /></TableCell>
            <TableCell><TextField size="small" required value={item.run || item.sequencing_run || ''} disabled={!editable} onChange={(event) => update(index, { run: event.target.value || null })} inputProps={{ 'aria-label': `Run ${item.measurement_id}` }} /></TableCell>
            <TableCell><Checkbox checked={item.technical_failure} disabled={!editable} onChange={(event) => update(index, { technical_failure: event.target.checked })} inputProps={{ 'aria-label': `Technical failure ${item.measurement_id}` }} /></TableCell>
          </> : template === 'input_degradation' ? <>
            <TableCell><TextField size="small" required type="number" value={item.input_ng || ''} disabled={!editable} onChange={(event) => update(index, { input_ng: Number(event.target.value) || null })} inputProps={{ min: 0, step: 'any', 'aria-label': `Input ng ${item.measurement_id}` }} /></TableCell>
            <TableCell><TextField size="small" required type="number" value={item.dv200 ?? ''} disabled={!editable} onChange={(event) => update(index, { dv200: event.target.value === '' ? null : Number(event.target.value) })} inputProps={{ min: 0, max: 100, step: 'any', 'aria-label': `DV200 ${item.measurement_id}` }} /></TableCell>
            <TableCell><TextField size="small" required value={item.sequencing_run || ''} disabled={!editable} onChange={(event) => update(index, { sequencing_run: event.target.value || null })} inputProps={{ 'aria-label': `Sequencing run ${item.measurement_id}` }} /></TableCell>
          </> : template === 'multifactor' ? <>
            <TableCell><TextField size="small" required value={item.extraction_method || ''} disabled={!editable} onChange={(event) => update(index, { extraction_method: event.target.value || null })} inputProps={{ 'aria-label': `Extraction method ${item.measurement_id}` }} /></TableCell>
            <TableCell><TextField size="small" required type="number" value={item.input_ng || ''} disabled={!editable} onChange={(event) => update(index, { input_ng: Number(event.target.value) || null })} inputProps={{ min: 0, step: 'any', 'aria-label': `Input ng ${item.measurement_id}` }} /></TableCell>
            <TableCell><TextField size="small" required value={item.run || ''} disabled={!editable} onChange={(event) => update(index, { run: event.target.value || null })} inputProps={{ 'aria-label': `Run ${item.measurement_id}` }} /></TableCell>
          </> : <>
            <TableCell><TextField size="small" required value={item.condition || ''} disabled={!editable} onChange={(event) => update(index, { condition: event.target.value || null })} inputProps={{ 'aria-label': `Condition ${item.measurement_id}` }} /></TableCell>
            <TableCell><TextField size="small" type="number" value={item.quality_metric ?? ''} disabled={!editable} onChange={(event) => update(index, { quality_metric: event.target.value === '' ? null : Number(event.target.value) })} inputProps={{ step: 'any', 'aria-label': `Quality metric ${item.measurement_id}` }} /></TableCell>
            <TableCell><TextField size="small" required value={item.run || ''} disabled={!editable} onChange={(event) => update(index, { run: event.target.value || null })} inputProps={{ 'aria-label': `Run ${item.measurement_id}` }} /></TableCell>
          </>}
          <TableCell><TextField size="small" value={item.operator || ''} disabled={!editable} onChange={(event) => update(index, { operator: event.target.value || null })} inputProps={{ 'aria-label': `Operator ${item.measurement_id}` }} /></TableCell>
          <TableCell><TextField size="small" value={item.reagent_lot || ''} disabled={!editable} onChange={(event) => update(index, { reagent_lot: event.target.value || null })} inputProps={{ 'aria-label': `Reagent lot ${item.measurement_id}` }} /></TableCell>
          <TableCell><TextField size="small" type="number" value={item.processing_order || ''} disabled={!editable} onChange={(event) => update(index, { processing_order: Number(event.target.value) || null })} inputProps={{ min: 1, 'aria-label': `Processing order ${item.measurement_id}` }} /></TableCell>
          <TableCell><TextField size="small" required={!item.include} value={item.exclusion_reason || ''} disabled={!editable || item.include} onChange={(event) => update(index, { exclusion_reason: event.target.value || null })} inputProps={{ 'aria-label': `Exclusion reason ${item.measurement_id}` }} /></TableCell>
        </TableRow>)}</TableBody>
      </Table>
      {assignments.length === 0 && <Stack p={3}><Typography color="text.secondary">Select a prepared Expression Bundle to map its measurements.</Typography></Stack>}
    </TableContainer>
  )
}
