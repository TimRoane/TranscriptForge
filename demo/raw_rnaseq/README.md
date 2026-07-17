# Raw RNA-seq ingestion template

The generated `paired/` and `single/` studies demonstrate the Phase 5 ingestion and execution
contracts. Upload every `read1` file with role
`fastq_r1`, every `read2` file with role `fastq_r2`, and the sheet with role `sample_sheet`.

Required columns:

- `sample_id`: stable biological-sample identifier using letters, digits, dots, underscores, or hyphens.
- `lane_id`: optional for one-row samples and required when a sample has multiple rows; lane IDs
  must be unique within each biological sample.
- `read1`: exact uploaded R1 basename ending in `.fastq`, `.fq`, `.fastq.gz`, or `.fq.gz`.
- `read2`: exact uploaded R2 basename, or blank for a single-end dataset.

Repeat `sample_id` across lane rows; additional columns are preserved as sample metadata and must
agree across those rows. A dataset must be uniformly paired-end or uniformly single-end. Ingestion
freezes file identifiers, sizes, SHA-256 checksums, lane inventory, layout,
strandedness, and the pinned reference-definition checksum before workflow execution.

`generate.py` deterministically creates four control/treated samples, valid gzip-compressed FASTQ,
and a four-transcript checksum-pinned reference. The paired study splits every biological sample
over two lanes while preserving its designed totals. It contains biological mock effects:
`ENSGFIX000001` is control-high, `ENSGFIX000002` is treatment-high, and the remaining genes are
stable. The single-end study uses the same design to exercise the alternate workflow branch.

The tiny reference is acceptance-test-only. Production ingestion exposes only the separately pinned
GENCODE reference under `references/human/`.
