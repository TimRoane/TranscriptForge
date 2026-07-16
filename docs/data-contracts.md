# Data contracts

TranscriptForge has four versioned cross-language JSON contracts:

1. Dataset Manifest — declares modality, source kind, identifiers, inputs, and checksums.
2. Expression Bundle Manifest — inventories immutable prepared assays, metadata, QC, mappings, and provenance.
3. Analysis Request — freezes analysis type, selected assay, parameters, inclusions, exclusions, and seed.
4. Result Manifest — describes summary values, generic result sections, artifacts, warnings, and downloads.

Schemas live in `schemas/` and use semantic `schema_version` fields. Producers write into a temporary directory, validate the complete contract, and atomically publish it. Consumers reject unknown major versions and preserve unknown compatible fields where practical.

The implemented matrix path accepts either matrix orientation, preserves immutable raw integer inputs, aligns exact sample IDs with metadata, and creates a reusable Expression Bundle. Bundles contain canonical assays, preserved sample metadata, feature-mapping reports, bounded previews, shared QC, input checksums, software versions, and an immutable archive.

Differential-expression result bundles include complete and thresholded tables, the exact R design
matrix, an explicit contrast definition, method diagnostics, session information, plot-ready JSON,
static SVGs, and a self-contained report. P-value distributions always use 20 bins over `[0, 1]`
and separately report unavailable values. Top-feature heatmaps select at most 30 rows using the
published results ordering, use log2 normalized counts for DESeq2, TMM-normalized log2 CPM for
edgeR QL and limma-voom, or the input log-expression assay for limma, and then standardize each feature to a z-score. Their contract retains feature effects,
adjusted p-values, sample metadata, assay/scale provenance, and the deterministic sample ordering.
Each new differential-expression run also publishes a tested-feature-by-sample normalized-expression
table. DESeq2 rows contain log2 normalized counts plus one; edgeR QL and limma-voom rows contain
TMM-normalized log2 CPM; limma rows retain the fitted input log-expression scale. Count-derived
edgeR/voom result tables use average log2 CPM as their abundance column, while edgeR leaves standard
error unavailable rather than deriving one from its quasi-likelihood F statistic. The result table carries optional gene symbols, the exact contrast, and method
labels so API pagination, filtering, sorting, filtered downloads, and gene-detail views remain
read-only projections of immutable run artifacts.

Saved candidate signatures are database records derived from that immutable result boundary. Each
draft stores the ordered feature identifiers, a snapshot of their complete result rows, the source
project/prepared-dataset/analysis/run identifiers, the source result artifact identifier and
SHA-256 checksum, and the table filters and ordering active when it was saved. The API only accepts
features present in the successful source run and labels every draft as research-use candidate
generation rather than independent validation.
