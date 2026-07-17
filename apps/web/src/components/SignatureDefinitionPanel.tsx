import UploadFileRoundedIcon from '@mui/icons-material/UploadFileRounded'
import {
  Alert,
  Button,
  Chip,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  fetchSignatureDefinitions,
  uploadSignatureDefinition,
  type SignatureDefinition,
} from '../api/client'
import { ErrorState, LoadingState } from './ApiState'

export function SignatureDefinitionPanel({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [definitionFormat, setDefinitionFormat] = useState<
    SignatureDefinition['definition_format']
  >('gene_list')
  const [identifierType, setIdentifierType] = useState<
    SignatureDefinition['identifier_type']
  >('ensembl_gene_id')
  const [file, setFile] = useState<File | null>(null)
  const definitions = useQuery({
    queryKey: ['signature-definitions', projectId],
    queryFn: ({ signal }) => fetchSignatureDefinitions(projectId, signal),
    enabled: Boolean(projectId),
  })
  const upload = useMutation({
    mutationFn: () => uploadSignatureDefinition(projectId, {
      name,
      description: description || undefined,
      definitionFormat,
      identifierType,
      file: file as File,
    }),
    onSuccess: async () => {
      setName('')
      setDescription('')
      setFile(null)
      await queryClient.invalidateQueries({
        queryKey: ['signature-definitions', projectId],
      })
    },
  })

  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Stack spacing={2.5}>
        <div>
          <Typography variant="overline" color="secondary.main" fontWeight={750}>
            Signature library
          </Typography>
          <Typography variant="h5" fontWeight={700}>Reusable signature definitions</Typography>
          <Typography color="text.secondary" mt={0.5}>
            Upload a tab-separated gene list with a gene_id header and optional weight column,
            or a standard GMT collection. The source and parsed definition are checksum-frozen.
          </Typography>
        </div>

        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }}>
          <TextField
            label="Signature name"
            size="small"
            value={name}
            onChange={(event) => setName(event.target.value)}
            sx={{ minWidth: 210 }}
          />
          <TextField
            select
            label="File format"
            size="small"
            value={definitionFormat}
            onChange={(event) => setDefinitionFormat(
              event.target.value as SignatureDefinition['definition_format'],
            )}
            sx={{ minWidth: 150 }}
          >
            <MenuItem value="gene_list">Gene-list TSV</MenuItem>
            <MenuItem value="gmt">GMT collection</MenuItem>
          </TextField>
          <TextField
            select
            label="Identifier namespace"
            size="small"
            value={identifierType}
            onChange={(event) => setIdentifierType(
              event.target.value as SignatureDefinition['identifier_type'],
            )}
            sx={{ minWidth: 190 }}
          >
            <MenuItem value="ensembl_gene_id">Ensembl gene ID</MenuItem>
            <MenuItem value="gene_symbol">Gene symbol</MenuItem>
            <MenuItem value="entrez_id">Entrez ID</MenuItem>
          </TextField>
          <Button component="label" variant="outlined" startIcon={<UploadFileRoundedIcon />}>
            {file?.name ?? 'Choose file'}
            <input
              hidden
              type="file"
              accept={definitionFormat === 'gmt' ? '.gmt,text/plain' : '.tsv,text/tab-separated-values'}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </Button>
        </Stack>
        <TextField
          label="Description (optional)"
          size="small"
          multiline
          minRows={2}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
        <Button
          variant="contained"
          onClick={() => upload.mutate()}
          disabled={!name.trim() || !file || upload.isPending}
          sx={{ width: 'fit-content' }}
        >
          {upload.isPending ? 'Uploading…' : 'Upload signature definition'}
        </Button>
        {upload.isError && <Alert severity="error">{upload.error.message}</Alert>}

        {definitions.isPending && <LoadingState label="Loading signature definitions…" />}
        {definitions.isError && <ErrorState error={definitions.error} />}
        {definitions.data?.length === 0 && (
          <Typography color="text.secondary">No reusable signature definitions yet.</Typography>
        )}
        {definitions.data?.map((definition) => (
          <Paper key={definition.id} variant="outlined" sx={{ p: 2, bgcolor: 'background.default' }}>
            <Stack spacing={1}>
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                <Typography fontWeight={700}>{definition.name}</Typography>
                <Chip size="small" label={definition.definition_format === 'gmt' ? 'GMT' : 'Gene list'} />
                <Chip size="small" label={definition.identifier_type.replaceAll('_', ' ')} />
                {definition.weighted && <Chip size="small" color="secondary" label="Weighted" />}
              </Stack>
              <Typography variant="body2" color="text.secondary">
                {definition.set_count} set{definition.set_count === 1 ? '' : 's'} ·{' '}
                {definition.unique_identifier_count.toLocaleString()} unique identifiers ·{' '}
                {definition.duplicate_identifier_count.toLocaleString()} duplicates collapsed
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                Definition SHA-256: {definition.manifest_sha256}
              </Typography>
            </Stack>
          </Paper>
        ))}
      </Stack>
    </Paper>
  )
}
