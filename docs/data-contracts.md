# Data contracts

TranscriptForge has five versioned cross-language JSON contracts:

1. Dataset Manifest — declares modality, source kind, identifiers, inputs, and checksums.
2. Expression Bundle Manifest — inventories immutable prepared assays, metadata, QC, mappings, and provenance.
3. Analysis Request — freezes analysis type, selected assay, parameters, inclusions, exclusions, and seed.
4. Result Manifest — describes summary values, generic result sections, artifacts, warnings, and downloads.
5. Enrichment Summary — freezes the source result, gene-set collection, parameters, ranked-list results, and over-representation results.

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

When requested, the R runner verifies a bundled GMT file against its versioned metadata and
publishes an Enrichment Summary plus ranked-list and over-representation TSVs and a static overview.
The ranked analysis uses a signed `-log10(p)` feature ranking, a frozen seed, and gene-label
permutations. Over-representation uses the tested-feature universe and the jointly thresholded
differential-expression foreground. The summary records the collection namespace, version, source,
license, GMT SHA-256, source-result SHA-256, set-size limits, permutation count, and DE thresholds.
Bundled demo sets are synthetic experiment controls and are labeled accordingly; they are not
presented as curated biological pathways.

Raw RNA-seq ingestion adds two contracts before any read-processing workflow can run. A Reference
Bundle Definition pins the human assembly, annotation provider/release, upstream asset URLs and
checksums, Salmon version, and decoy-index parameters. A Raw RNA-seq Ingestion Manifest normalizes
the tab-separated sample sheet, groups explicit lane rows into logical biological samples, and
freezes every uploaded read's internal file identifier, basename, size, SHA-256, lane identity,
library layout, strandedness, sample metadata, and reference-definition SHA-256.
Uploading another sample sheet or FASTQ makes the previous active ingestion manifest stale.

Raw preparation consumes that manifest without rediscovering samples. Its Reference Materialization
Manifest records the definition digest, exact Salmon version, upstream MD5 and local SHA-256 values,
gentrome/decoy/tx2gene hashes, and every derived index-file hash. tximport publishes gene and
transcript counts, TPM, effective lengths, original Salmon outputs, and annotation-aware QC; the
canonical Expression Bundle advertises analysis-ready `raw_counts`, `log_expression`, and `tpm`
plus a preserved transcript-level abundance assay with explicit rounded gene-count semantics.

Saved candidate signatures are database records derived from that immutable result boundary. Each
draft stores the ordered feature identifiers, a snapshot of their complete result rows, the source
project/prepared-dataset/analysis/run identifiers, the source result artifact identifier and
SHA-256 checksum, and the table filters and ordering active when it was saved. The API only accepts
features present in the successful source run and labels every draft as research-use candidate
generation rather than independent validation.

Affymetrix ingestion uses a checksum-pinned Platform Adapter plus a Microarray Ingestion Manifest.
The adapter explicitly declares accepted CEL formats and chip aliases, the `oligo` platform package,
the transcript-cluster annotation package, the RMA target, and supported probe-to-gene aggregation
rules. Ingestion freezes exact CEL-to-sample assignments and checksums without inferring sample names
from filenames. Preparation revalidates the adapter digest and CEL files, runs RMA, preserves both
probe-set and Ensembl-gene log-expression assays, publishes probe/transcript-cluster/gene mappings,
and records package versions, session information, QC tables, plots, and parameters in the canonical
Expression Bundle.

A Signature Definition freezes an uploaded gene-list TSV or GMT collection before evaluation. It
records the exact source checksum, declared identifier namespace, optional finite weights, every
parsed set and entry, and requested/unique/duplicate totals. Mapping uses immutable Expression Bundle
feature metadata with explicit Ensembl version stripping and exact symbol or Entrez matching. It
never silently chooses an ambiguous feature: mapped, missing, ambiguous, and duplicate identifiers
remain visible per set and in aggregate. A Signature Mapping Report freezes both the Signature
Definition manifest checksum and Expression Bundle checksum, retains identifier-to-feature mappings
and optional weights, and is stored with checksum-bearing missing- and ambiguous-identifier TSVs.
A Signature Scores document records the exact mapping-report and Expression Bundle checksums,
explicit method formula, final scored-feature counts, constant-feature exclusions, every aligned
sample score and metadata record, mapping coverage, warnings, and language/package versions. Frozen
GSVA/ssGSEA requests additionally retain gene-set size bounds and all exposed algorithm parameters;
post-constant-filter sizes are revalidated before fitting. The complete score and final-gene TSVs
remain immutable run artifacts alongside the JSON contract.
