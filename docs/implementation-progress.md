# TranscriptForge implementation progress

Last updated: 2026-07-18

This file is the durable continuation checkpoint for Codex sessions. Update it after every implementation session.

## Current position

- Active roadmap phase: Phase 9 — classifier development and validation
- Active milestone: Phase 9 software complete; prospective biological validation pending
- Current task: Prepare GSE140494 without touching GSE32646 outcomes, lock the development model, then execute the frozen external protocol once
- Overall milestone status: Binary and multiclass design, nested-CV execution, model export, inference, API/UI, and external-cohort support are complete. GSE32646 and the success thresholds are prospectively frozen, but no real independent-cohort performance has been calculated, so Phase 9 remains scientifically open.

## Completed

- [x] Imported the full implementation plan.
- [x] Established the Phase 0 monorepo structure.
- [x] Added initial architecture, data-contract, and local-development documentation.
- [x] Added Docker Compose definitions for PostgreSQL, Redis, MinIO, API, worker, and web.
- [x] Added FastAPI health/version boundary and Celery application skeleton.
- [x] Added React/Vite application shell and API health integration.
- [x] Added a Nextflow DSL2 smoke entry workflow.
- [x] Added baseline API and web tests, lint configuration, and CI workflow.
- [x] Verified the complete Docker Compose stack, API health endpoint, web shell, and a real Celery round trip.
- [x] Completed Phase 0 acceptance criteria.
- [x] Added typed SQLAlchemy entities for projects, datasets, dataset files, prepared datasets, analyses, runs, artifacts, and model records.
- [x] Added the initial asynchronous Alembic migration, including the prepared-dataset/run relationship.
- [x] Added project and dataset create, list, retrieve, update, and delete API operations.
- [x] Enforced human-only scope and valid modality/source-kind combinations at the API boundary.
- [x] Added dataset file upload with generated object keys, atomic local writes, SHA-256 checksums, and namespace confinement.
- [x] Added integration tests for CRUD, cascade behavior, scientific input guardrails, uploads, and storage traversal rejection.
- [x] Added an API-connected project dashboard and project detail page.
- [x] Added a guarded three-step dataset wizard with modality-aware source options.
- [x] Added matrix and sample-metadata upload controls with checksum confirmation.
- [x] Added an S3-compatible storage adapter and automatic MinIO bucket initialization.
- [x] Completed Phase 1 acceptance criteria.
- [x] Added Draft 2020-12 Dataset Manifest, Expression Bundle, Analysis Request, Result Manifest, and Sample Metadata contracts.
- [x] Added a valid count-matrix demo manifest and schema compatibility tests.
- [x] Added a streaming matrix/metadata validator supporting features-by-samples and samples-by-features orientations.
- [x] Added raw-count numeric, finite, nonnegative, integer, duplicate-ID, row-width, missing-value, and exact sample-alignment checks.
- [x] Added capped actionable findings, matrix/metadata summaries, and bounded previews.
- [x] Added a versioned Validation Report JSON Schema.
- [x] Added atomic validation report and checksum-bearing Dataset Manifest generation.
- [x] Added the first functional `PREPARE_DATASET` Nextflow process, which owns matrix validation and publishes both contracts.
- [x] Added durable `POST /api/datasets/{id}/validate` run creation with frozen dataset, file, checksum, and validation parameters.
- [x] Added Celery dispatch and a shell-free Nextflow argument-array launcher with checksum-verified input staging.
- [x] Added durable `QUEUED`, `STARTING`, `RUNNING`, `SUCCEEDED`, and `FAILED` transitions, including dataset status restoration on infrastructure failure.
- [x] Captured Nextflow session/run identifiers, exit status, stdout, stderr, log, trace, execution report, timeline, and DAG.
- [x] Indexed validation reports, Dataset Manifests, logs, and provenance outputs as downloadable artifacts.
- [x] Added run status, validation history, artifact listing/download, validation report, and Dataset Manifest API routes.
- [x] Connected dataset cards to validation launch, short polling, terminal status, actionable findings, matrix orientation previews, and contract downloads.
- [x] Added a canonical Expression Bundle builder for both matrix orientations with disk-backed transposition for samples-by-features inputs.
- [x] Preserved immutable source counts, emitted canonical raw-count and log2-CPM assays, and retained all sample metadata columns.
- [x] Added explicit Ensembl identity/version mapping, mapping coverage, unmapped-feature reports, and sum-based duplicate resolution.
- [x] Added shared per-sample library-size, detected-feature, zero-fraction, review-flag, JSON, TSV, and SVG QC outputs.
- [x] Added schema-valid bundle manifests, input checksums, parameters, software versions, previews, and downloadable bundle archives.
- [x] Split Nextflow validation and preparation entries and added a cohesive `BUILD_EXPRESSION_BUNDLE` process.
- [x] Added durable preparation runs, immutable prepared-dataset versions, and preparation artifact indexing.
- [x] Added preparation launch/polling to dataset cards and a prepared-dataset page with QC visualization, mapping summaries, assay inventory, and downloads.
- [x] Completed all Phase 2 acceptance criteria.
- [x] Added saved, listable, and cloneable dimension-reduction analyses with validated PCA configuration.
- [x] Added immutable PCA run requests tied to a specific prepared-dataset version and Expression Bundle checksum.
- [x] Added durable analysis run launch, Celery dispatch, and `QUEUED` through terminal state tracking.
- [x] Added a `RUN_ANALYSIS` Nextflow entry and deterministic NumPy SVD PCA over canonical assays.
- [x] Canonicalized PCA component signs so identical inputs and seeds emit byte-identical results.
- [x] Emitted schema-valid Result Manifests, coordinates, loadings, explained variance, plot-ready JSON, and a research-use HTML report.
- [x] Indexed PCA results plus complete Nextflow logs, trace, report, timeline, and DAG as downloadable artifacts.
- [x] Added PCA launch controls to the Expression Bundle page with component count and feature-scaling options.
- [x] Added an auto-updating PCA result page with selectable component axes, sample metadata coloring, hover details, variance bars, metrics, reruns, downloads, and provenance.
- [x] Completed the PCA vertical-slice acceptance criteria for Phase 3.
- [x] Added a deterministic 72-library, 36-donor paired genotype-treatment demonstration with three balanced batches and 2,000 simulated genes.
- [x] Added documented treatment, genotype, interaction, batch, sex, negative-treatment, donor-noise, and null ground-truth feature blocks.
- [x] Added reproducible demo generation and idempotent API seeding commands that validate, prepare, and analyze the study through the real worker path.
- [x] Generalized saved dimension-reduction configuration for PCA, hierarchical clustering, UMAP, and t-SNE with method-specific parameter validation.
- [x] Added most-variable-feature selection, explicit scaling, correlation/Euclidean distance, average/complete/Ward linkage, and cluster-count controls.
- [x] Added hierarchical clustering outputs: dendrogram contract, sample correlation heatmap, cluster assignments, linkage matrix, Result Manifest, and report.
- [x] Added seeded UMAP and t-SNE implementations with configurable neighbors, minimum distance, and perplexity.
- [x] Added deterministic rerun tests for clustering, UMAP, and t-SNE on the larger experiment.
- [x] Generalized the Nextflow analysis process, artifact indexing, and JSON result endpoints across all four Phase 3 methods.
- [x] Added method-specific launch controls plus interactive PCA/UMAP/t-SNE coordinates, dendrogram, heatmap, cluster summaries, and downloads to the GUI.
- [x] Added a reusable report generator that emits deterministic Quarto sources and research-use HTML fallbacks for all four dimension-reduction methods.
- [x] Installed pinned Quarto 1.9.38 in the worker and rendered self-contained HTML reports inside the Nextflow process boundary.
- [x] Added deterministic static SVG exports for PCA/embedding coordinates, explained variance, hierarchical dendrograms, and sample correlation heatmaps.
- [x] Indexed Quarto sources, rendered reports, and all static plots as immutable downloadable run artifacts and surfaced them in the result page.
- [x] Added frontend interaction coverage for UMAP method configuration and non-PCA dendrogram/heatmap result rendering.
- [x] Completed every Phase 3 task and acceptance criterion, including GUI launch, worker/Nextflow execution, durable state, interactive results, downloads, and deterministic reruns.
- [x] Generalized saved-analysis creation contracts for dimension reduction and differential expression while preserving the existing endpoint.
- [x] Added typed differential-expression design, contrast, filtering, FDR, fold-change, independent-filtering, shrinkage, and method-routing configuration.
- [x] Expanded the versioned Analysis Request JSON Schema with type-specific dimension-reduction and differential-expression request contracts.
- [x] Added immutable Expression Bundle metadata discovery with categorical/numeric inference, level inventories, missingness counts, and assay inventories.
- [x] Added server-side model-matrix construction, reference-level handling, interaction encoding, rank checks, replication checks, design-cell counts, and imbalance warnings.
- [x] Added automatic assay routing from raw counts to DESeq2 and from log-scale expression to limma, with incompatible method/assay combinations blocked.
- [x] Added design-options and design-preview API endpoints and required a valid preview before a differential-expression analysis can be saved.
- [x] Added a Phase 4 GUI builder for assay, method, primary variable, numerator, denominator, covariate, subject/block, FDR, and absolute fold-change settings.
- [x] Added a saved differential-expression design page showing the generated formula, plain-English contrast, sample counts, thresholds, and model rank.
- [x] Kept differential-expression run launch explicitly disabled until the R/Nextflow execution module was implemented.
- [x] Added an official Bioconductor 3.23 production image definition with DESeq2, limma, edgeR, and jsonlite.
- [x] Added a version-pinned development-worker R 4.5 / DESeq2 1.46 / limma 3.62 runtime for direct execution under the Nextflow test profile.
- [x] Added an independent R-side bundle, count, metadata, reference-level, replication, formula, model-column, and rank validation boundary.
- [x] Enforced the versioned Analysis Request before Nextflow launch and the Result Manifest before artifact indexing in the durable worker.
- [x] Compared the R design against the immutable server preview before model fitting and fail with actionable disagreement diagnostics.
- [x] Added raw-count filtering, deterministic DESeq2 fitting, independent filtering, optional normal-prior shrinkage, and explicit numerator-minus-denominator contrasts.
- [x] Routed frozen differential-expression requests through a dedicated Nextflow process while preserving all Phase 3 dimension-reduction routing.
- [x] Emitted complete and significant result tables, design matrix, contrast definition, method diagnostics, R session information, and a schema-valid Result Manifest.
- [x] Added deterministic volcano and MA JSON/SVG outputs plus a self-contained Quarto research-use report.
- [x] Indexed all differential-expression outputs and full Nextflow provenance as immutable artifacts and exposed volcano/MA JSON endpoints.
- [x] Enabled run/rerun controls, live state polling, failure display, interactive volcano/MA views, summary metrics, and result downloads on the saved design page.
- [x] Generalized the shared R runner for limma empirical-Bayes fitting over continuous log-expression assays.
- [x] Constructed explicit numerator-minus-denominator limma contrasts from validated model rows and recorded the exact design-coefficient weights for auditability.
- [x] Kept method semantics explicit: limma reports average log2 expression and does not claim count filtering, DESeq2 independent filtering, or fold-change shrinkage.
- [x] Surfaced method warnings in the result GUI and added frontend coverage for limma-specific MA-axis semantics.
- [x] Re-ran DESeq2 after the shared-runner refactor and confirmed its scientific tables and plots remain byte-identical.
- [x] Added a deterministic 20-bin p-value distribution with explicit finite and missing-value counts for both DESeq2 and limma.
- [x] Added top-30 expression heatmaps using log2 DESeq2 normalized counts or the limma input log-expression assay, followed by per-feature z-scoring.
- [x] Preserved paired-study interpretation by ordering blocked designs by subject then contrast and retaining sample metadata plus feature-level effect annotations.
- [x] Added plot-ready JSON, static SVG, Result Manifest entries, Quarto report sections, durable artifact indexing, and API routes for both new visualizations.
- [x] Added interactive p-value bars and a metadata-annotated expression heatmap to the shared differential-expression result page.
- [x] Kept full heatmap z-scores in the JSON contract while clamping only the static renderer to its documented -3 to +3 color scale.
- [x] Made Nextflow provenance observers launcher-owned and overwrite-safe so concurrent runs and failed-process finalization cannot mask the primary workflow error.
- [x] Added gene symbols, exact contrast labels, and method labels to the common differential-expression result table while preserving method-specific abundance columns.
- [x] Published a deterministic normalized-expression table for every tested feature: log2 DESeq2 normalized counts plus one or the limma input log-expression assay.
- [x] Added server-side ID/symbol search, FDR and absolute-fold-change filters, significant-only filtering, sortable columns, bounded pagination, and filtered TSV downloads.
- [x] Added per-feature detail APIs joining model statistics, 72 sample-level expression values, full sample metadata, and contrast-group summaries.
- [x] Added a responsive result explorer, clickable volcano/MA points and table rows, and a gene-detail drawer with an expression strip plot and group means.
- [x] Kept older runs compatible: their result tables remain explorable and their detail view clearly requests a rerun when normalized profiles are unavailable.
- [x] Added a deterministic runner-level paired-study fixture with 100 annotated features split into positive, negative, null, and low-count truth blocks.
- [x] Added direct R CLI assertions that frozen formula and model-rank disagreements fail before either statistical engine fits a model or publishes a Result Manifest.
- [x] Added DESeq2 acceptance assertions for exact low-count exclusion, tested/filtered diagnostics, numerator-minus-denominator direction, feature annotations, and normalized profiles.
- [x] Added shared DESeq2/limma assertions for positive and negative known-effect recovery, bounded null calls, explicit contrast direction, and complete sample-level profiles.
- [x] Added `make test-r` and `make test-all` developer targets and a dedicated CI job that builds the pinned worker image and executes the scientific harness.
- [x] Added a dedicated candidate gene-signature entity and Alembic migration, separate from trained model records.
- [x] Added run- and project-scoped signature APIs that require a successful differential-expression source run and reject features absent from its immutable result table.
- [x] Frozen each signature's ordered feature identifiers, complete result-row snapshots, source artifact identifier/checksum, and active table-selection criteria.
- [x] Added result-page row and page selection for up to 500 genes, a named draft workflow, saved-draft summaries, and explicit independent-validation warnings.
- [x] Exercised the feature against the live paired-treatment DESeq2 run and preserved a visible three-gene demonstration draft.
- [x] Added edgeR 4.4.2 to the pinned development worker and strengthened the dedicated Bioconductor image version check.
- [x] Implemented edgeR quasi-likelihood with explicit low-count filtering, TMM normalization, robust dispersion estimation, and an explicit QL contrast test.
- [x] Implemented limma-voom with the same filter/TMM boundary, voom precision weights, explicit contrast weights, and moderated inference.
- [x] Generalized result parsing and the shared result GUI for average-log2-CPM abundance while leaving edgeR standard error unavailable instead of inventing an estimate.
- [x] Extended method diagnostics, normalized profiles, heatmaps, MA semantics, reports, and manifests across all four differential-expression engines.
- [x] Extended API routing, frozen request validation, frontend method selection, and the deterministic R acceptance harness for both new methods.
- [x] Added optional seeded ranked-list enrichment and hypergeometric over-representation analysis after any differential-expression engine.
- [x] Added versioned synthetic demo and scientific acceptance GMT collections with namespace, source, license, set count, and verified SHA-256 provenance.
- [x] Added a cross-language Enrichment Summary contract that freezes the selected collection, source differential-expression checksum, ranking metric, seed-dependent permutation count, size limits, and DE thresholds.
- [x] Added immutable enrichment JSON/TSV/SVG artifacts, worker-side schema enforcement, API retrieval, Result Manifest/report integration, and dashboard comparison tables.
- [x] Added explicit UI and report warnings that the bundled demo controls are not a curated biological pathway database and that enrichment is exploratory rather than independent validation.
- [x] Extended the deterministic R harness with known positive, negative, and null gene sets and verified ranked direction, ORA separation, collection checksum, source checksum, and complete artifact publication.
- [x] Completed every Phase 4 task and acceptance criterion, including assay-aware method selection, pre-fit rank rejection, internally consistent result views, optional enrichment, candidate signatures, and reports carrying design, contrast, thresholds, and session provenance.
- [x] Added an owner-facing technical/content debt register with explicit manual decisions and exit criteria for storage cleanup, authentication, curated gene sets, reference policy, cancellation, validation corpora, legal language, AWS Batch, and upgrade governance.
- [x] Added Draft 2020-12 Reference Bundle Definition and Raw RNA-seq Ingestion Manifest contracts.
- [x] Pinned GENCODE 50 on GRCh38.p14 with Ensembl 116 provenance, official upstream asset URLs/MD5 values, Salmon 1.11.4, k=31, and a full-primary-genome decoy index strategy.
- [x] Added synchronous sample-sheet ingestion for uniformly paired- or single-end FASTQ datasets with safe sample IDs, exact R1/R2 basename resolution, duplicate assignment rejection, arbitrary validated metadata columns, and bounded sheet size/sample counts.
- [x] Frozen internal dataset-file identifiers, storage URIs, sizes, SHA-256 checksums, layout, strandedness, reference-definition SHA-256, and reference/tool versions in a persisted normalized ingestion manifest.
- [x] Added source-aware upload-role guardrails, dataset-file inventory, pinned-reference catalog, ingestion creation/retrieval endpoints, and automatic stale-manifest detection after any newer FASTQ or sample-sheet upload.
- [x] Added FASTQ R1/R2 multi-upload controls, sample-sheet upload, strandedness selection, ingestion validation, file counts, provenance, warnings, and normalized sample previews to the project dashboard.
- [x] Added deterministic four-sample paired- and single-end FASTQ experiments with known control/treatment expression shifts and a checksum-pinned tiny full-decoy-style reference isolated from the production catalog.
- [x] Corrected the nonexistent Salmon 1.12.0 pin to official release 1.11.4 and pinned architecture-specific release-archive SHA-256 values in the worker build.
- [x] Added reference materialization that validates definition drift, upstream MD5 values, local SHA-256 values, Salmon version, gentrome/decoy/tx2gene hashes, and every derived index file before atomically caching by definition digest.
- [x] Added current-manifest-only Nextflow modules for input revalidation, paired/single FastQC, fastp, Salmon quantification, tximport gene summaries, MultiQC, and raw Expression Bundle construction.
- [x] Added raw dataset preparation orchestration, immutable run/artifact indexing, prepared-dataset creation, dashboard launch/status controls, and direct MultiQC/counts/TPM downloads.
- [x] Published raw counts, log expression, and TPM in the canonical bundle with explicit rounded-estimated-count semantics and complete reference/tool provenance.
- [x] Added `make test-raw-rnaseq`; paired and single workflows recover all designed counts exactly, the second layout reuses the shared reference index, and a repeated paired run caches all 17 reference/sample/summary tasks.
- [x] Extended raw ingestion to one explicit row per sequencing lane, with stable lane IDs, consistent per-sample metadata, exact file assignment, and deterministic logical-sample merging for paired and single-end inputs.
- [x] Upgraded the frozen ingestion manifest to 1.1.0 with lane counts and per-sample lane inventories while retaining implicit `lane_1` compatibility for one-row sample sheets.
- [x] Extended checksum-derived reference mappings with gene name, gene type, and sequence-name annotations and versioned the materialization cache to prevent reuse of older derived mapping formats.
- [x] Preserved transcript counts, TPM, effective lengths, every original Salmon `quant.sf` plus key provenance files, and a transcript-level abundance assay inside the immutable Expression Bundle.
- [x] Added annotation-aware mitochondrial/ribosomal percentages, processed/mapped reads, mapping rate, detected genes, library size, mean sample correlation, and conservative PCA-distance review flags without automatic exclusion.
- [x] Added transcript/QC download links to the dataset dashboard and expanded the deterministic paired fixture to eight lanes across four biological samples without changing its known gene-level effects.
- [x] Added an `awsbatch` Nextflow profile that requires a digest-pinned ECR scientific image, uses S3 work storage, assigns a dedicated task role, bounds submissions/retries, and terminates unschedulable jobs.
- [x] Replaced the initially considered shared EFS cache with an immutable S3 reference cache keyed by reference-definition SHA-256 and materializer version; completion manifests publish last and every restored byte is revalidated.
- [x] Staged local reference fixture directories as explicit Nextflow inputs so the same workflow graph can execute on remote Batch workers.
- [x] Added Terraform for a scale-to-zero EC2/Spot Batch environment, encrypted/versioned/private S3, immutable encrypted ECR, KMS-encrypted EBS and logs, bounded IAM roles, and an optional cost-alert email.
- [x] Added the AWS threat model, deployment guide, digest-pinned scientific-image builder, environment renderer, offline/read-only preflight, and a cost-explicit local-versus-Batch scientific parity harness.
- [x] Added offline tests for S3 reference-cache publication/restoration, AWS profile validation, and exact/canonical scientific-artifact comparison plus Terraform CI validation.
- [x] Deferred owner-account AWS provisioning and cost-incurring Batch acceptance without blocking the local roadmap; the reviewed infrastructure remains available under `infra/aws`.
- [x] Added Draft 2020-12 Affymetrix Platform Adapter and Microarray Ingestion Manifest contracts plus an explicit Human Gene 1.0 ST adapter registry entry.
- [x] Added synchronous CEL ingestion with Calvin/XDA format detection, chip-alias validation, exact sample-metadata mapping, checksum freezing, aggregation selection, staleness detection, and explicit unsupported-platform errors.
- [x] Added microarray platform catalog, ingestion creation/retrieval, and preparation routing through durable API, Celery, Nextflow, artifact indexing, and prepared-dataset records.
- [x] Added a Bioconductor 3.23 scientific image with `oligo`, `pd.hugene.1.0.st.v1`, `hugene10sttranscriptcluster.db`, and `jsonlite`.
- [x] Added RMA background correction, quantile normalization, probe-set summarization, probe-to-transcript-cluster-to-Ensembl mapping, and highest-MAD/median/mean gene aggregation.
- [x] Preserved probe-set and gene-level log-expression assays and published raw/normalized distributions, PCA, correlation, array metrics/flags, parameters, package versions, and R session provenance.
- [x] Extended the canonical Expression Bundle for microarray provenance and a limma-compatible `log_expression` assay while removing count-specific library-size QC from this modality.
- [x] Added a checksum-pinned public NCBI GEO GSE39795/GPL6244 eight-CEL paired-donor fixture plus a repeatable `make test-microarray` RMA-to-bundle-to-limma acceptance path.
- [x] Added typed raw-CEL dashboard controls for multi-CEL and metadata uploads, explicit platform selection, highest-MAD/median/mean aggregation, stale-manifest warnings, ingestion diagnostics, sample previews, and preparation launch.
- [x] Added microarray-aware prepared-dataset rendering for array/probe/gene QC counts, immutable raw/normalized distribution, PCA and correlation plots, probe aggregation provenance, expression/mapping downloads, and R session information.
- [x] Added a schema-valid paired `~ donor + zone` limma request over four matched donors and asserted full-rank design, superficial-minus-deep contrast weights, all gene results, eight-sample normalized profiles, plots, tables, report source, and session provenance.
- [x] Completed every Phase 6 task and acceptance criterion: explicit platform validation, real RMA, probe/gene assays, documented aggregation, array QC, public downloads, unsupported-array errors, and limma over the resulting bundle.
- [x] Kept reusable uploaded signature definitions separate from provenance-frozen candidate-gene drafts selected from differential-expression results.
- [x] Added the Draft 2020-12 Signature Definition contract for checksum-frozen gene-list/GMT sources, identifier namespaces, optional weights, duplicate accounting, parsed sets, and source provenance.
- [x] Added project-scoped immutable `signature_definitions` persistence and Alembic migration `20260716_0003` with source/manifest URIs and checksums plus bounded summary fields.
- [x] Added safe multipart gene-list and GMT ingestion with UTF-8/NUL/size/set/entry/identifier validation, identical-duplicate collapse, conflicting-weight rejection, and deterministic parsed manifests.
- [x] Added project list/retrieve endpoints and prepared-bundle mapping for Ensembl gene IDs, gene symbols, and Entrez IDs with explicit version stripping, ambiguity handling, per-set coverage, mapped feature IDs, missing genes, and duplicate counts.
- [x] Added the Draft 2020-12 Signature Mapping Report contract with exact definition/bundle checksums, identifier-to-feature mappings, retained weights, coverage, missing identifiers, and ambiguities.
- [x] Persisted idempotent definition-to-bundle mappings in migration `20260716_0004` with immutable JSON report, missing-identifier TSV, and ambiguous-identifier TSV objects plus checksums and bounded database summaries.
- [x] Added mapping list and artifact-download endpoints and preserved cleanup behavior when database persistence fails after object publication.
- [x] Added project-page definition upload/inventory controls and prepared-bundle mapping controls that show mapped, missing, ambiguous, duplicate, and coverage evidence before scoring.
- [x] Guarded scoring behind an immutable mapping report and made every mapping artifact directly downloadable.
- [x] Extended saved analyses and frozen Analysis Requests with signature mapping identity/checksum, compatible log-expression assay enforcement, and mean-expression, mean-z-score, weighted-linear, and rank-based method contracts.
- [x] Added deterministic scientific implementations with explicit formulas: arithmetic mean expression; across-sample gene z-scores using sample standard deviation and visible constant-gene exclusion; unnormalized weighted linear sums; and within-sample percentile-rank means.
- [x] Added the Draft 2020-12 Signature Scores contract with complete mapping/bundle provenance, final feature counts, every per-sample score and aligned metadata, score ranges, method formula, and warnings.
- [x] Added the `RUN_SIGNATURE_SCORING` Nextflow process, worker contract validation, score/final-feature TSVs, static SVG, Quarto report, durable artifact indexing, and a score-result API endpoint.
- [x] Enabled prepared-bundle scoring launch controls with method selection and weighted-method eligibility, plus a live result page showing coverage, frozen checksums, score distributions, complete sample tables, warnings, downloads, and reruns.
- [x] Added first-class Bioconductor GSVA and ssGSEA methods with frozen gene-set size limits, GSVA kernel/tau/ranking options, and ssGSEA alpha/normalization options in API, JSON Schema, and GUI contracts.
- [x] Added an independent R signature runner that checksum-verifies the mapped Expression Bundle, explicitly removes constant genes, rejects post-filter gene sets outside the frozen size range, ignores weights with a visible warning, and runs the GSVA parameter-object API serially.
- [x] Added a dedicated `RUN_GSVA_SCORING` Nextflow route and Bioconductor 3.23 production container while retaining the Python route for the four core scoring methods.
- [x] Extended the shared Signature Scores contract and result page with language, runtime, implementation, and package-version provenance for both Python and R results.
- [x] Added deterministic R acceptance fixtures for positive/negative response sets, constant-gene exclusion, complete artifacts, package provenance, and byte-identical repeated GSVA/ssGSEA JSON results.
- [x] Added optional phenotype association to saved signature analyses with automatic categorical/numeric detection, selectable covariates, categorical subject/block fixed effects, replication checks, rank checks, and residual-degree-of-freedom rejection before launch.
- [x] Added adjusted two-group comparisons, multi-level omnibus tests, numeric slopes with raw Pearson correlations, Benjamini-Hochberg correction across signature sets, group summaries, exact model formulas/columns, and deterministic TSV/SVG outputs in both Python and Bioconductor scoring paths.
- [x] Added phenotype-aware categorical strip plots and numeric scatter plots to the signature result page, together with effect, p-value, FDR, correlation, model, and downloadable artifact presentation.
- [x] Added a checksum-frozen weighted Ensembl signature acceptance that builds independent RNA-seq raw-count/log2-CPM and microarray RMA-like Expression Bundles, maps the identical definition checksum into each bundle, and scores both through the production Python scientific boundary.
- [x] Added a Draft 2020-12 cross-modality acceptance contract with prespecified mapping, FDR, AUROC, direction-concordance, and distinct-raw-scale criteria plus deterministic repeat evidence and a dedicated Make target.
- [x] Made the platform boundary explicit in score warnings, reports, result pages, architecture, and demo documentation: raw score magnitudes are not comparable across RNA-seq, microarray, cohorts, or preprocessing pipelines; only prespecified within-dataset direction/ranking/association or standardized effects are compared.
- [x] Added a checksum-frozen public GSE39795 cartilage-zone benchmark with marker directions selected before scoring, explicit paired-donor association, and a versioned acceptance-result JSON Schema.
- [x] Evaluated mean expression, mean z-score, weighted linear, rank-based, GSVA, and ssGSEA against the same public Expression Bundle; all methods retained 100% marker mapping and recovered both expected directions at directional AUROC 1.0 and FDR below 0.05.
- [x] Prespecified the public benchmark thresholds: 80% recommended mapping coverage, four samples per group, expected direction for every set, directional AUROC at least 0.80, FDR at most 0.05, and a byte-identical repeated default run.
- [x] Selected mean z-score through a fixed preference order as the within-cohort product default, added a visible below-80% exploratory warning, and retained explicit language prohibiting transferable raw thresholds across cohorts, platforms, or preprocessing pipelines.
- [x] Added a reproducible containerized Make target that checksum-verifies the public bundle and marker definition, runs all Python/R scoring paths, validates the result contract, and reproduced the committed acceptance result byte-for-byte.
- [x] Completed every Phase 7 task and acceptance criterion, while retaining independent biological validation and mixed-effects policy as explicit scientific debt rather than overstating the technical benchmark.
- [x] Added a checksum-versioned cell-deconvolution registry covering EPIC, quanTIseq, MCP-counter, xCell, and external-only CIBERSORTx with execution status, reference choices, and explicit source documentation.
- [x] Typed every method as cell fraction or enrichment score with distinct units, composition constraints, and allowed within-sample versus between-sample comparisons; enrichment scores cannot be mislabeled as percentages.
- [x] Declared and enforced method-specific organism, feature level, gene-symbol namespace, assay name, scale, value type, negative-value, and provisional minimum-reference-overlap requirements against the immutable Expression Bundle manifest and feature metadata.
- [x] Added global and prepared-bundle method-capability APIs that show compatible assays, configuration availability, execution availability, and every blocking reason without guessing from filenames.
- [x] Extended saved analyses with deconvolution parameters and froze the registry version/checksum, complete method record, resolved reference, exact assay descriptor/checksum, output type, and overlap threshold.
- [x] Added versioned Analysis Request and Deconvolution Results contracts requiring reference/overlap provenance, typed estimates, and fraction-only composition summaries; schema tests reject fraction/enrichment semantic mismatches.
- [x] Added a prepared-bundle deconvolution setup panel and saved-design page that keep method semantics visible and intentionally disable execution until a pinned runner, reference checksum, and acceptance fixture pass.
- [x] Pinned the Bioconductor 3.22 `quantiseqr` 1.18.0 source archive by SHA-256 and froze the TIL10 signature, mRNA-scaling, noisy-gene, and tumor-exclusion file checksums in a schema-validated reference manifest.
- [x] Recorded EPIC 1.1.7 and its exact upstream tag/commit in a machine-readable license gate; default images do not redistribute or expose EPIC because its academic agreement requires separate acceptance and restricts redistribution/network use.
- [x] Added an audited quanTIseq R runner that verifies the frozen request, Expression Bundle, TPM assay, reference manifest, installed package/reference files, human organism, linear nonnegative values, and exact sample order before fitting.
- [x] Added explicit feature-to-gene-symbol mapping, blank-symbol exclusion, sum-based duplicate-symbol collapse, optional tumor-gene exclusion, effective TIL10 overlap enforcement, and downloadable gene-level overlap evidence.
- [x] Published structured fraction JSON, long-format TSV, composition audits, static SVG, Quarto report, R session information, checksums, package/algorithm provenance, and a schema-valid Result Manifest.
- [x] Routed quanTIseq through a dedicated Nextflow process and checksum-pinned scientific container, validated its result contract in the durable worker, and indexed every fraction/reference/report artifact.
- [x] Enabled quanTIseq run/rerun/cancel controls and a result page with per-sample stacked fractions, complete percentage tables, overlap metrics, warnings, downloads, and frozen provenance; runnable methods are selected by default in setup.
- [x] Added a deterministic four-mixture acceptance fixture recovering B-cell, NK-cell, CD8 T-cell, and neutrophil dominance while checking 99%+ overlap, duplicate/blank audits, sum-to-one compositions, complete artifacts, and byte-identical repeated JSON.
- [x] Pinned MCPcounter 1.2.0 and xCell 1.1.0 to exact upstream commits/source SHA-256 values, froze the CC0 MCP-counter marker file and serialized xCell reference-object checksums, and installed both only in the containerized scientific toolchain.
- [x] Generalized the audited R runner across linear TPM fractions and log-scale enrichment input while retaining method-specific negative-value rules, sum-versus-mean duplicate-symbol aggregation, package/reference checks, exact sample order, and effective overlap evidence.
- [x] Implemented MCP-counter mean-marker abundance scores and the xCell ssGSEA/calibration/spillover pipeline for RNA-seq and microarray Expression Bundles; both publish arbitrary-score results without composition summaries or percentage conversion.
- [x] Added separate enrichment-pattern SVGs and a result-type-aware dashboard with within-population z-score coloring, complete raw-score tables, explicit comparison limits, generic package provenance, downloads, and run/rerun/cancel controls.
- [x] Added known-marker MCP-counter/xCell acceptance mixtures that recover B-lineage, NK, endothelial, and fibroblast enrichment, require 95% reference overlap, verify complete artifact publication and non-compositional semantics, and produce byte-identical repeated JSON.
- [x] Added a prepared-bundle comparison API that selects the latest successful result per saved deconvolution analysis, validates artifact completeness, and excludes malformed results with visible reasons.
- [x] Partitioned comparison sections by result type, unit, exact assay semantics, sample order, and Expression Bundle checksum so cell fractions, enrichment scores, and incompatible inputs cannot be combined.
- [x] Added exact population-ID-and-label intersection across method-specific references plus per-population Pearson concordance for compatible methods with at least three samples, while declining inferred ontology/reference crosswalks and zero-variance correlations.
- [x] Added a cross-method result panel with links to contributing analyses, reference/overlap/composition evidence, shared-population counts, concordance tables, semantic warnings, exclusions, and a clear single-method empty state.
- [x] Promoted CIBERSORTx to an available external-import adapter without adding credentials, proprietary resources, terms automation, or a native/cloud execution dependency.
- [x] Added a multipart relative-result import boundary requiring the exact TPM assay, explicit relative-fraction declaration, signature name/version/checksum/gene count, mixture/signature overlap, batch mode, permutations, external runtime version/run ID/time, and the original export.
- [x] Added strict UTF-8 TSV/CSV parsing, exact Expression Bundle sample-set validation and canonical reordering, unique population checks, finite 0–1 fractions, per-sample sum-to-one tolerance, size bounds, and schema validation before persistence.
- [x] Materialized imported results as immutable successful external-import runs with original-source, normalized-table, structured-result, result-manifest, and frozen-provenance artifacts; native rerun attempts are explicitly rejected.
- [x] Added a CIBERSORTx import form and imported-result dashboard with relative-fraction plots/tables, signature/runtime/source checksums, external-run evidence, downloads, research-use caveats, and compatibility-aware comparison participation.
- [x] Completed every Phase 8 implementation task and acceptance criterion while retaining EPIC legal review, independent validation, and empirical overlap calibration under TD-015.
- [x] Added a strict Phase 9 binary-classifier request contract for elastic-net logistic regression over immutable gene-level log expression, including outcome direction, grouping, cohort, feature filtering, class weighting, repeated nested-CV dimensions, metric, calibration, threshold, bootstrap, and permutation settings.
- [x] Added deterministic classifier design-options and preview APIs that require exactly two complete outcome levels, detect repeated experimental units, reject infeasible outer or inner folds, and prove zero group overlap before a model can be saved.
- [x] Frozen the complete outer-fold plan, class/group counts, expected repeated OOF coverage, training-fold-only preprocessing and feature-selection policy, inner-fold-only tuning policy, and evaluation-only outer-test role in every saved classifier analysis.
- [x] Kept classifier execution server-blocked until the scientific runner and leakage-trap acceptance test are implemented, preventing the design contract from implying unverified modeling capability.
- [x] Added a classifier setup panel with biological defaults, explicit outcome direction and experimental-unit grouping, nested-CV controls, fold audit, warnings, and a saved-analysis page that exposes the immutable leakage policy without a misleading run action.
- [x] Added API, JSON Schema, and frontend regression coverage for grouped deterministic previews, ungrouped repeated-unit rejection, request freezing, launch rejection, fold audit rendering, and exact save serialization.
- [x] Added a versioned binary-classifier result contract covering repeated OOF coverage, fold-specific tuning/calibration/threshold evidence, core metrics, feature stability, leakage scopes, bundle provenance, and software versions.
- [x] Implemented a deterministic elastic-net scientific runner that refits variance selection and standardization inside every inner and outer training partition, tunes C/L1 ratio only from inner validation predictions, and never exposes outer test samples to preprocessing or selection.
- [x] Implemented optional sigmoid calibration and Youden threshold selection exclusively from inner-training OOF decisions, followed by one evaluation-only probability for each outer test sample.
- [x] Recomputed the complete grouped split plan in the scientific runner and rejected any disagreement with the API-frozen plan, any inner/outer group overlap, incomplete inner predictions, or anything other than exactly one OOF prediction per sample per repeat.
- [x] Added deterministic known-signal recovery and an adversarial leakage-scope acceptance test that passes the production fit scopes and fails an intentionally incorrect implementation that observes an outer test sample.
- [x] Routed classifier requests through the durable worker and dedicated Nextflow process, validated classifier results before indexing, and published structured results, OOF predictions, feature stability, reports, and full workflow provenance as immutable artifacts.
- [x] Enabled run/rerun/cancel controls and added an initial classifier result dashboard with ROC-AUC, PR-AUC, balanced accuracy, Brier score, OOF completeness evidence, feature stability, downloads, and explicit internal-validation language.
- [x] Added complete per-repeat metrics, experimental-unit percentile-bootstrap confidence intervals, ROC and precision-recall coordinates, calibration intercept/slope and reliability bins, a confusion matrix, and deterministic combined diagnostic SVG.
- [x] Added full label permutations that repeat fold-local variance selection, preprocessing, inner-CV hyperparameter tuning, calibration, and outer-fold fitting for every permutation, plus an empirical p-value and leakage-safe learning curve.
- [x] Added random-forest and histogram-gradient-boosting comparison models over the identical repeated outer splits, with algorithm selection and parameter tuning confined to each outer training partition; elastic net remains the only locked primary model.
- [x] Fit the final elastic-net model only after internal validation, froze selected features, scaling, coefficients, intercept, calibration, decision threshold, and training scope, and published a research-only model card, machine-readable inference schema, and blank input template.
- [x] Indexed every diagnostic/model/card/schema artifact in the durable worker and persist successful locked models in the model registry; the result dashboard now shows confidence bounds, permutation evidence, curves, per-repeat metrics, comparison models, and the external-validation warning.
- [x] Implemented `PREDICT_WITH_MODEL` as a real Nextflow entry workflow. It validates locked-model dimensions and assay compatibility, blocks any missing required feature or non-finite value, reproduces the frozen preprocessing/calibration/threshold, and publishes per-sample predictions, exact feature overlap, input checksums, and a schema-valid Result Manifest.
- [x] Added an explicit multinomial elastic-net mode for 3–20 outcome classes, with nullable binary direction, macro-metric choices, every-class outer/inner feasibility checks, deterministic grouped fold plans, and method-specific request validation.
- [x] Implemented deterministic multinomial grouped repeated nested CV with fold-local variance filtering and scaling, inner-only C/L1 tuning, complete OOF class-probability vectors, macro ROC-AUC/F1, balanced accuracy, log loss, group-bootstrap intervals, one-vs-rest ROC coordinates, confusion evidence, classwise feature stability, and fully re-tuned label permutations.
- [x] Added locked multinomial coefficient/intercept/scaling artifacts, model cards and inference schemas; `PREDICT_WITH_MODEL` now validates and applies binary or multiclass models and emits normalized class probabilities with checksummed provenance.
- [x] Added binary/multiclass setup and result interfaces, including explicit classifier-type selection, compatible outcome filtering, macro metrics, multiclass confusion/stability evidence, locked-artifact downloads, and regression coverage for request serialization and rendering.
- [x] Prospectively selected GSE140494 for model development and the disjoint Osaka University GSE32646 cohort for one-use external validation, after rejecting overlapping MD Anderson accessions as independent evidence. A new schema-valid protocol freezes GPL570/RMA preparation, endpoint mapping, the truth-label embargo, ROC-AUC at least 0.65 with lower 95% bound above 0.50, secondary metrics, and prohibited post-hoc changes. No external expression performance has been inspected or claimed.
- [x] Reworked the root README as a hiring-manager-facing product overview with real RNA-seq and public-microarray user-flow screenshots, architecture, verification evidence, local setup, repository map, and explicit constraints.
- [x] Materialized a live eight-array GSE39795 project through the public API, published its 23,702-gene/257,430-probe-set RMA Expression Bundle, and ran a full-rank paired `~ donor + zone` limma analysis for the portfolio walkthrough.
- [x] Corrected server design preview so numeric-looking declared block identifiers are encoded categorically, matching the independent R scientific boundary and preserving paired-design semantics.
- [x] Corrected Expression Bundle design defaults to prioritize biological variables over per-sample identifiers and to offer repeated numeric-looking subject identifiers as blocks; the public microarray page now opens directly on the valid `~ donor + zone` paired design.
- [x] Added a product-facing application home with workflow framing, capability summaries, recent-project access, and direct workspace/start-project actions; `/projects` now owns project management explicitly.
- [x] Added project deletion from workspace cards and project detail pages with exact-name confirmation, cascade/retention warnings, API error feedback, cache invalidation, and post-delete navigation.
- [x] Corrected project deletion for nonempty execution graphs with migration `20260717_0005`: dataset/prepared/analysis run references and dependent model/signature records now cascade, while the preparation-run back-reference safely clears to break the ownership cycle.
- [x] Removed roadmap-phase labels from every user-visible application section and renamed the two persisted development smoke projects that still exposed phase numbers.
- [x] Replaced the repository MIT grant with the unmodified PolyForm Noncommercial 1.0.0 terms, aligned package and bundled synthetic-collection metadata, updated the public README, and recorded the remaining legal-review and prior-distribution limitations under TD-008.
- [x] Promoted saved analyses from small trailing chips to a high-visibility continuation panel near the top of each Expression Bundle, with full-width typed navigation actions; clarified differential-expression handoff with “Save design & continue to run,” explanatory copy, and a distinct “Run differential expression” action on the saved-analysis page.

## Verification

- `pytest`: 3 API/worker tests passed under Python 3.12 and Python 3.13.
- `ruff`: passed.
- `mypy --strict`: passed for 14 source files.
- `vitest`: 1 frontend integration test passed under Node.js 22.
- `eslint`: passed with zero warnings.
- Vite production build: passed.
- `npm audit`: zero known vulnerabilities.
- `docker compose config --quiet`: passed.
- Docker development images: built successfully.
- Full Compose startup: PostgreSQL, Redis, MinIO, API, worker, and web all started; stateful services and API reported healthy.
- API smoke request returned the expected typed health payload.
- Celery worker responded to inspection and consumed `transcriptforge.system.worker_health` through Redis.
- Nextflow `RUN_DEMO`: passed and emitted the expected `health.json`; a resumed run used the task cache.
- `git diff --check`: passed.
- Updated backend test suite: 9 tests passed under Python 3.13.
- Updated strict typing: passed for 25 API source files.
- Initial migration applied successfully to PostgreSQL and reports `20260716_0001 (head)`.
- `alembic check`: no model/schema drift detected against PostgreSQL.
- Live PostgreSQL API smoke path passed: create project, create count-matrix dataset, upload and hash a matrix, retrieve it, and delete the project.
- Updated backend suite: 18 tests passed under Python 3.13.
- Frontend suite: 2 dashboard/navigation tests passed under Node.js 22.
- Frontend TypeScript production build and ESLint passed.
- S3 storage contract tests passed, including generated keys, checksums, deletion, foreign-bucket rejection, and traversal rejection.
- Live MinIO upload/delete smoke test passed after automatic bucket creation.
- Rebuilt Compose stack passed API health and client-side project-route fallback checks.
- All five Phase 2 JSON Schemas passed Draft 2020-12 meta-schema validation.
- The count-matrix demo manifest validates; a microarray/FASTQ mismatch is rejected.
- Updated combined Python suite: 30 tests passed.
- Strict mypy passed across 36 API and analysis source files; Ruff passed.
- The validator passed valid, invalid, both-orientation, CLI, schema, and manifest tests.
- Nextflow `PREPARE_DATASET` executed successfully and emitted schema-valid `validation_report.json` and `dataset_manifest.json`.
- Nextflow `-resume` reused the completed validation process when inputs and code were unchanged.
- Frontend suite: 3 dashboard/navigation/validation tests passed under Node.js 22; ESLint and the production TypeScript/Vite build passed.
- The rebuilt Compose stack passed API and web health checks with the pinned Java/Nextflow worker runtime.
- A live API-to-Redis-to-Celery-to-Nextflow validation completed in about three seconds with state `SUCCEEDED`, report status `VALID`, a persisted Nextflow session UUID, and nine indexed artifacts.
- Docker Compose configuration and `git diff --check` passed.
- Expression Bundle tests passed for features-by-samples, samples-by-features, Ensembl version stripping, duplicate aggregation, unchanged count values, bundle archiving, QC, and schema validation.
- Nextflow `PREPARE_DATASET` completed the validation-to-bundle chain and published a schema-valid Expression Bundle.
- Frontend suite: 4 dashboard/navigation/validation/prepared-dataset tests passed; ESLint and the production TypeScript/Vite build passed.
- A live durable preparation completed in about four seconds with persisted prepared-dataset version 1, QC `PASS`, 100% mapping coverage, a Nextflow session UUID, and 14 indexed artifacts.
- Alembic reported no model/schema drift; the rebuilt worker registered both validation and preparation tasks with bounded concurrency.
- Updated combined Python suite: 33 tests passed under Python 3.13; Ruff passed.
- Strict mypy passed across 42 API and analysis source files.
- Frontend suite: 4 tests passed under Node.js 22; ESLint and the production TypeScript/Vite build passed.
- A live API-to-Redis-to-Celery-to-Nextflow PCA completed in about four seconds with a persisted Nextflow session UUID and 14 indexed artifacts.
- A second live run of the same saved PCA produced identical SHA-256 hashes for coordinates, loadings, explained variance, both plot contracts, and the Result Manifest.
- Updated combined Python suite: 38 tests passed, including large-demo reproducibility and the complete dimension-reduction suite.
- Strict mypy passed across 44 API and analysis source files; Ruff and `git diff --check` passed.
- Frontend suite: 4 tests passed; ESLint and the Node.js 22 production build passed.
- The 72-sample demonstration validated and prepared successfully through API, Redis, Celery, and Nextflow with QC `PASS` and 100% synthetic identifier mapping.
- Live PCA, hierarchical clustering, UMAP, and t-SNE runs all reached `SUCCEEDED` and published their method-specific result and provenance artifacts.
- The large-study PCA shows the intended controlled structure: PC1 treatment centroids are approximately +11.99 for vehicle and -11.99 for stimulated, with PC1 explaining 13.3% of variance.
- Phase 3 combined Python suite: 38 tests passed; Ruff passed and strict mypy passed across 46 source files.
- Phase 3 frontend suite: 6 integration tests passed; ESLint and the production TypeScript/Vite build passed.
- The rebuilt worker reports Quarto 1.9.38 and Nextflow 25.10.4; Docker Compose configuration and `git diff --check` passed.
- A fresh live PCA run (`521e8949-6b65-41bb-8a2b-c57baa049c13`) succeeded through API, Redis, Celery, and Nextflow, emitted 18 indexed artifacts, and produced a report carrying the `quarto-1.9.38` generator marker.
- A fresh live hierarchical-clustering run (`2865ee18-4b6c-4eca-a578-7c85ade1a043`) succeeded and indexed its dendrogram SVG, correlation heatmap SVG, assignments, linkage table, Quarto source, rendered report, and complete provenance set.
- Phase 4 foundation Python suite: 41 tests passed; Ruff passed and strict mypy passed across 47 source files.
- Phase 4 frontend suite: 7 integration tests passed; ESLint and the production TypeScript/Vite build passed.
- The live 72-sample bundle exposed seven metadata variables and both `raw_counts` and `log_expression` assays through the design-options contract.
- Live validation correctly rejected `~ subject_id + batch + treatment` because batch is confounded with subject, and rejected `~ subject_id + genotype + treatment` because genotype is constant within subject.
- Live validation accepted the paired design `~ subject_id + treatment` at full rank 37/37, routed raw counts to DESeq2, and confirmed 36 stimulated versus 36 vehicle samples.
- Saved live Phase 4 design: `e033fb5c-0516-4a74-9bf8-8e0b77d1eeaa` (`Paired treatment response`).
- Phase 4 DESeq2 slice: 41 backend tests passed; Ruff passed and strict mypy passed across 47 source files.
- Phase 4 DESeq2 frontend: 7 integration tests passed; ESLint and the Node.js 22 production build passed.
- The rebuilt development worker reports R 4.5.0, DESeq2 1.46.0, jsonlite 1.9.1, Quarto 1.9.38, and Nextflow 25.10.4.
- Live paired DESeq2 run `91aa6799-2517-494e-b437-bb2d2386f0c4` independently confirmed 72 samples and a full-rank 37/37 `~ subject_id + treatment` model, tested 2,000 features, called 254 significant features, and indexed 20 artifacts.
- Identical live rerun `1cad3c72-740c-4795-98c1-60094de4adfe` produced byte-identical complete/significant tables, design matrix, contrast, diagnostics, Result Manifest, plot JSON, plot SVG, Quarto source, and R session information.
- Post-guardrail live run `7dd98963-4d2b-4417-9aae-1f92ed03ad0f` passed frozen-request validation before launch and Result Manifest validation before its 20 artifacts were indexed.
- Known-effect recovery matched the simulated direction: all 150 treatment-up genes were significant with median log2 fold change +1.392, 92/100 treatment-down genes were significant with median -1.244, and none of 1,430 null/subject-noise genes passed the configured joint FDR/effect threshold.
- Phase 4 limma slice: 41 backend tests passed; Ruff and strict mypy passed across 47 source files. Eight frontend integration tests, ESLint, and the production build passed.
- The development worker now reports limma 3.62.2 alongside R 4.5.0 and DESeq2 1.46.0.
- Saved live limma analysis `2a13c140-0f8a-4617-bb59-e17b386469f9` routed `log_expression` plus `auto` to limma and independently confirmed the same full-rank 37/37 paired design.
- Live limma run `7e156689-c521-439d-b85a-8d4425fadaf9` tested 2,000 features, called 253 significant features, and indexed 20 immutable artifacts with a schema-valid Result Manifest.
- Limma recovered all 150 treatment-up genes at median log2 fold change +1.339, 99/100 treatment-down genes at median -1.360, and zero of 1,430 null/subject-noise genes at the joint threshold.
- Corrected limma rerun `0693fb6d-11d1-480a-91c9-36c63980bc2c` produced byte-identical tables, diagnostics, plot JSON/SVG, and R session information.
- Post-refactor DESeq2 run `e7663f5a-50b5-4811-8f3c-b633110fdf6d` succeeded with the original 254 calls and byte-identical tables, design matrix, and plots.
- Phase 4 visualization slice: 41 backend tests passed; Ruff and strict mypy passed across 47 source files. Eight frontend integration tests, ESLint, and the production build passed.
- Live limma run `bdda45f6-71f6-4a02-bc67-20f64c375a27` and DESeq2 run `2381d439-1a1d-42ea-8241-e0bd9c6d9f95` each indexed 24 artifacts, including both JSON/SVG visualization pairs.
- Both live p-value contracts contain 20 bins summing to all 2,000 finite tests with zero missing values.
- Both live heatmaps contain 30 features by 72 samples; sampled rows have mean zero and sample standard deviation one, and each donor's vehicle/stimulated pair remains adjacent.
- Limma rerun `cd953616-1295-49be-8b29-a6120ee76676` and DESeq2 rerun `2870e9e4-d78a-40f6-ab08-8c218821f7b6` produced byte-identical p-value JSON/SVG, heatmap JSON/SVG, scientific tables, Result Manifests, and report sources.
- Final concurrent limma run `5410e8c8-b500-4a86-8d4d-60320a0edcf1` and DESeq2 run `65f217a7-26f5-4f4f-94e2-8dda22a36f9b` both succeeded and indexed 24 artifacts after the static heatmap renderer correction.
- Concurrent reruns `abf67d02-ee04-4a2a-88a9-3eefe0f93c3b` (limma) and `0e3bda9a-bd79-4277-afa2-df9e5117b67d` (DESeq2) produced byte-identical SHA-256 hashes for all 16 scientific contracts, tables, report sources, and static plots checked per engine.
- Final live contracts again contained 20 p-value bins summing to 2,000 tests and 30-by-72 expression heatmaps with assay-correct source semantics.
- Final verification after the renderer and provenance corrections: 41 Python tests passed; Ruff and strict mypy passed across 47 source files; R parsing, Docker Compose configuration, and `git diff --check` passed.
- Phase 4 table/gene-detail verification: 41 Python tests and eight frontend integration tests passed; Ruff, ESLint, strict mypy across 48 source files, the production TypeScript/Vite build, R parsing, Docker Compose configuration, and `git diff --check` passed.
- Live limma run `d49f46fe-f45f-49d6-a977-02d9b9f0df97` and DESeq2 run `7aa45ee3-8309-4804-8378-8d507908ad49` each succeeded concurrently and indexed 25 artifacts, including normalized expression for all 2,000 tested features.
- Live threshold queries returned the expected 253 limma and 254 DESeq2 significant features; significant-only downloads contained the matching rows plus one header.
- A non-top feature detail request returned all 72 samples and two contrast groups of 36 samples for both engines, confirming gene detail is not limited to the top-30 heatmap selection.
- Reruns `9ea1a8e2-c675-4d66-983c-7f7f9838f2b9` (limma) and `518ad76b-5878-4463-a858-6c93b190539e` (DESeq2) produced byte-identical SHA-256 hashes for all 17 checked scientific artifacts per engine.
- The R acceptance harness rejected both formula and rank disagreements with their actionable diagnostics and did not publish a Result Manifest for either failed case.
- DESeq2 tested 90/100 fixture features, filtered exactly all ten low-count rows, recovered 15/15 positive and 15/15 negative effects, and called 0/60 null features.
- Limma tested all 100 fixture features, recovered 15/15 positive and 15/15 negative effects, and called 0/60 null features.
- Final scientific-harness regression: `make test-r` passed in a fresh one-off worker container; 41 Python tests and eight frontend integration tests passed; Ruff, ESLint, strict mypy across 48 source files, the production frontend build, Docker Compose validation, and `git diff --check` passed.
- Saved-signature regression: 42 Python tests and eight frontend integration tests passed; Ruff, strict mypy across 51 source files, the R DESeq2/limma acceptance harness, ESLint, the Node.js 22 production build, Docker Compose validation, and `git diff --check` passed.
- Alembic migration `20260716_0002` applied successfully to PostgreSQL and `alembic check` reported no model/schema drift.
- Live signature draft `32c84994-7980-413a-8822-1cfd5f282114` froze three result rows from DESeq2 run `518ad76b-5878-4463-a858-6c93b190539e`; its stored source checksum matched result artifact `906a2d17-c247-476e-9f3a-ec12ff4ea57a` exactly.
- Four-engine regression: 44 Python tests and eight frontend integration tests passed; Ruff, strict mypy across 51 source files, ESLint, the Node.js 22 production build, Docker Compose validation, and `git diff --check` passed.
- The expanded R harness passed for DESeq2, limma, edgeR QL, and limma-voom. Both new count engines filtered exactly 10/100 low-count controls, recovered 15/15 positive and 15/15 negative effects, and called 0/60 null features.
- The rebuilt live worker reports R 4.5.0, edgeR 4.4.2, and limma 3.62.2.
- Live edgeR analysis `c31e8833-39a1-4aa8-a33b-ca87b5df90d4` run `3f9699ba-abf3-4951-a406-63dcb65003e8` and limma-voom analysis `339a7348-f43b-402e-be0a-555c69a0267c` run `973c4025-0bb5-414d-b007-3b89d6a7d5ee` each tested all 2,000 features, called 256 significant features, and indexed 25 artifacts.
- edgeR QL recovered 150/150 treatment-up and 94/100 treatment-down genes; limma-voom recovered 150/150 and 93/100 respectively; both called 0/1,430 null/subject-noise genes.
- Concurrent reruns `93082641-1646-4ac4-97c7-59d1a7a12014` (edgeR QL) and `2af50b87-1271-49eb-a23b-53125b379404` (limma-voom) produced identical SHA-256 hashes for all 18 non-Nextflow artifacts checked per engine.
- Phase 4 enrichment regression: 46 Python tests and eight frontend integration tests passed; Ruff, strict mypy across 51 source files, ESLint, the Node.js 22 production build, R parsing, the four-engine scientific harness, JSON Schema validation, and `git diff --check` passed.
- The enriched R acceptance case preserved positive and negative ranked-list direction and its ORA results called both known-effect sets while leaving the null control nonsignificant.
- Live edgeR enrichment analysis `53509cd4-532c-4173-b505-a65e43101b6b`, final run `ff176636-dcc0-4970-b4ec-b3f799d1fe0a`, succeeded with 29 artifacts, verified collection SHA-256 `5b727116570594783d809ed31c725e853397da9f314a6eab15d80bcb4a360b2a`, and froze the exact differential-expression result checksum and random seed `20260716`.
- The live ranked analysis called the synthetic treatment-up control at NES 2.150 and adjusted p 0.0164; ORA recovered all 150 treatment-up and 94 treatment-down control features while all unrelated/null controls remained nonsignificant.
- Comparison run `6dbf2098-8481-4877-9ee2-e51308f8598d` produced byte-identical differential-expression results, Enrichment Summary, ranked-list TSV, ORA TSV, and enrichment SVG.
- The final live Quarto source explicitly records design, contrast, FDR and fold-change thresholds, R/Bioconductor versions, and the full `session_info.txt` provenance artifact.
- Phase 5 ingestion regression: 51 Python tests and nine frontend integration tests passed; Ruff, strict mypy across 52 source files, ESLint, the Node.js 22 production build, JSON Schema validation, Docker Compose validation, and `git diff --check` passed.
- Live raw RNA-seq project `8656a2b2-769b-4064-bb9f-4432704a6cb6`, dataset `208c8167-3c8a-4af8-ba06-9a6c2362ad60`, ingested two paired-end sample mappings and four checksum-frozen placeholder input objects with reverse strandedness; genuine tiny FASTQ content is deliberately assigned to the next QC/quantification slice.
- The live ingestion contract validated against Draft 2020-12 and froze reference-definition SHA-256 `b7f1c8cceb1981448536870508af4a25d9df755480569a228798d76a2e663090` plus all three official GENCODE upstream MD5 values.
- Phase 5 local workflow regression: 53 Python tests passed; Ruff and strict mypy passed across 55 source files; paired- and single-end Nextflow workflows completed with FastQC 0.12.1, fastp 0.24.0, Salmon 1.11.4, tximport 1.34.0, and MultiQC 1.32.
- Both four-sample raw fixtures recovered the designed gene counts exactly. Paired MultiQC found eight FastQC, four fastp, and four Salmon reports; both bundles expose raw counts, log expression, and TPM.
- The single-end run reused the paired run's checksum-keyed Salmon index (`cache_hit: true`), and the final paired `-resume` trace marked all 17 workflow tasks `CACHED`.
- The old live placeholder ingestion references the corrected nonexistent Salmon 1.12.0 definition and is intentionally stale; re-ingestion is required before it can launch the new workflow.
- The corrected production definition SHA-256 is `0344a9bb3250b0a8e095edd6171cdc8cfd0663b1fedc088d4a7edf114416b1a3`; the live placeholder dataset was returned to `draft` so the dashboard does not imply it is executable.
- Phase 5 lane/transcript/QC regression: 55 Python tests and nine frontend integration tests passed; Ruff, strict mypy, ESLint, the Node.js 22 production build, R parsing, Docker Compose validation, and `git diff --check` passed.
- The eight-lane paired fixture merged to four logical samples and recovered the same exact designed gene/transcript totals as the single-lane layout; the paired `-resume` run cached all 17 tasks and the single run reused the shared materialization-1.1.0 reference cache.
- Identifier-aware QC recovered the designed mitochondrial percentages (10.20%–48.98%) and ribosomal percentages (10.20%–48.98%), reported 100% fixture mapping, and emitted no sample-exclusion actions.
- The refreshed development worker reports Salmon 1.11.4, FastQC 0.12.1, fastp 0.24.0, tximport 1.34.0, and MultiQC 1.32 and responds to Celery inspection.
- Phase 5 cloud-execution foundation: 59 combined Python tests passed; Ruff and strict mypy passed across 55 source files; the AWS Batch profile rendered with a digest-pinned image, task role, and S3 reference prefix.
- Terraform 1.13 initialized with locked AWS provider 6.55.0, formatted cleanly, and validated the Batch/S3/KMS/ECR/Logs/IAM/budget deployment without applying resources.
- The rebuilt worker reports AWS CLI 2.27.49, and the complete paired/single raw RNA-seq acceptance passed after remote-safe reference-asset staging and ordinary-file index publication; the repeated paired run cached all 17 tasks.
- Live AWS provisioning and local/Batch checksum evidence were intentionally not attempted because no owner account/VPC/budget/data-locality decisions or cost authorization were supplied.
- Phase 6 regression: 67 combined Python tests passed; Ruff passed; strict mypy passed across 57 source files; R parsing, Docker Compose validation, and `git diff --check` passed.
- The pinned Bioconductor image reports Bioconductor 3.23, `oligo` 1.76.0, `pd.hugene.1.0.st.v1` 3.14.1, and `hugene10sttranscriptcluster.db` 8.8.0.
- Real public CEL acceptance completed RMA on eight deep/superficial arrays from four donors and published 257,430 probe sets plus 23,702 mapped Ensembl genes with array QC `PASS`.
- The final canonical bundle validated against the Expression Bundle schema, advertises gene-level differential expression, contains both gene and probe assays plus four microarray QC plots, and omits count-specific library-size QC.
- Paired public limma acceptance retained all eight arrays, independently rebuilt a full-rank 5/5 `~ donor + zone` design, tested all 23,702 genes, preserved complete normalized profiles, and published every expected result/provenance artifact with the explicit superficial-minus-deep direction.
- Phase 6 GUI regression: 11 frontend integration tests passed; ESLint and the Node.js 22 TypeScript/Vite production build passed.
- Phase 7 ingestion foundation: 70 combined Python tests passed; Ruff and strict mypy passed across 58 source files; migration `20260716_0003` applied and Alembic reported no model/schema drift.
- Weighted-list acceptance preserved source and manifest checksums, collapsed one identical duplicate, mapped versioned Ensembl IDs at 2/3 coverage, and exposed the missing identifier. GMT acceptance retained per-set duplicate accounting and conflicting weights failed explicitly.
- Phase 7 durable-mapping regression: 71 combined Python tests and 12 frontend integration tests passed; Ruff, strict mypy across 58 source files, ESLint, and the Node.js 22 production build passed.
- Migration `20260716_0004` applied successfully to PostgreSQL, became Alembic head, and `alembic check` reported no model/schema drift.
- Weighted mapping acceptance idempotently persisted one record, retained both mapped weights, froze definition and bundle checksums, and reproduced the JSON report plus exact missing/ambiguous TSV downloads.
- Phase 7 core-scoring regression: 77 combined Python tests and 13 frontend integration tests passed; Ruff, strict mypy across 60 source files, ESLint, and the Node.js 22 production build passed.
- Exact-value tests covered mean expression, weighted linear, rank-based, and mean z-score methods; repeated runs produced byte-identical result contracts/tables/plots/reports, and the z-score final-feature table explicitly excluded a constant gene.
- A direct Nextflow signature-scoring acceptance published all seven expected result/report files from the canonical matrix fixture.
- Live API-to-Redis-to-Celery-to-Nextflow weighted analysis `32ea8043-4f86-4416-b3be-d205ebd685ee`, successful run `e664df9b-6af3-4d8d-a0a1-b54fbfe2b511`, scored 72 samples at 2/3 mapping coverage, indexed 14 artifacts, and exposed the frozen score contract through the API and GUI.
- Phase 7 GSVA/ssGSEA regression: 78 combined Python tests and 13 frontend integration tests passed; Ruff, strict mypy across 60 source files, ESLint, the Node.js 22 TypeScript/Vite build, Nextflow configuration, and `git diff --check` passed.
- The rebuilt development worker passed its pinned-package assertions with R 4.5.0,
  Bioconductor 3.22 repositories, GSVA 2.4.9, BiocParallel 1.40.0, DESeq2 1.46.0,
  and jsonlite 1.9.1.
- The containerized GSVA/ssGSEA acceptance experiment passed expected positive/negative direction,
  constant-feature exclusion, complete artifacts, software provenance, and byte-identical repeated
  JSON for both methods. The existing four-engine differential-expression and enrichment harness
  also passed unchanged against the rebuilt worker.
- The numeric-block regression passed and the live public microarray preview independently reported
  a full-rank 5/5 design for four matched donors and the superficial-versus-deep contrast.
- Live public microarray run `bdf17410-baaf-4a46-adb6-33789a03848c` tested all 23,702 genes through
  limma and succeeded with complete result, visualization, report, and Nextflow artifacts.
- The Docker-profile RMA process completed on all eight CEL files in the pinned Bioconductor image;
  the generic bundle-builder image's missing `ps` utility is recorded as TD-015 rather than hidden.
- Eight README-linked 1440-pixel-wide application screenshots were inspected and added under
  `docs/images/readme/` for the GitHub walkthrough, including the product home.
- Application-home/project-management regression: 14 frontend integration tests passed in the
  Node 22 container; ESLint and the production TypeScript/Vite build passed. The build retains the
  already-recorded bundle-size warning under TD-006.
- A live browser acceptance created a temporary project, kept deletion disabled until its exact name
  was entered, deleted it through the UI and public API, removed the card after cache invalidation,
  and confirmed that no temporary project record remained.
- Public-microarray design regression: 14 frontend integration tests passed, including automatic
  `zone` selection, superficial-versus-deep direction, numeric `donor` blocking, and full-rank 5/5
  validation. ESLint and the Node.js 22 production build passed, and a live headless-browser check
  found `Design valid`, `Rank 5/5`, and `~ donor + zone` with no blocked-design state.
- The existing public limma table was audited rather than relabeled: 23,702 genes were tested;
  2,084 have nominal p < 0.05, 665 have nominal p < 0.01, 53 have FDR < 0.20, and zero have FDR
  < 0.05. The README and TD-013 now explain this low-powered but biologically nonempty result.
- Saved-analysis navigation/handoff regression: 14 frontend integration tests passed, including the
  prominent saved-analysis link and save-to-run transition; ESLint and the Node.js 22 production
  build passed. The live public-microarray page was visually inspected at 1440 pixels and shows two
  saved differential-expression analyses as primary action cards above array QC.
- Project-cascade regression: 79 combined Python tests passed, including deletion of a project with
  a queued validation run; Ruff, strict mypy across 60 source files, Docker Compose validation, and
  `git diff --check` passed. Migration `20260717_0005` applied at PostgreSQL head with no model/schema
  drift. The live “Validation workflow smoke test” project then deleted with HTTP 204, removing its
  dataset, 11 run records, and 106 artifact-index records.
- Stopped the first live full-GENCODE raw RNA-seq preparation after confirming that reference
  materialization, rather than the tiny FASTQ fixture, dominated runtime; removed its abandoned 11 GB
  atomic-build directory and restored 10 GB of host capacity.
- Added end-to-end local cancellation for queued and executing validation, preparation, and analysis
  runs: durable `CANCELLING`/`CANCELLED` transitions, process-group termination, dataset-state
  restoration, in-app Stop actions, preserved launcher logs, and SIGTERM-aware reference temp cleanup.
- Corrected production GENCODE indexing with Salmon `--gencode` so pipe-delimited FASTA headers agree
  with GTF-derived transcript IDs, and bumped the immutable materialization schema to `1.2.0` so no
  incompatible index can be reused.
- Cancellation/reference regression: 85 combined Python tests and 15 frontend integration tests
  passed; Ruff, strict mypy across 61 source files, ESLint, and the production TypeScript/Vite build
  passed. The remaining frontend chunk-size warning stays tracked under TD-006.
- Refreshed the GitHub README walkthrough from the live application at 1440 pixels. The RNA-seq
  sequence now consistently uses TranscriptForge Visualization Study, visibly presents its 14 saved
  exploration, differential-expression, enrichment, and signature analyses, and retains the public
  Affymetrix ingestion/RMA/limma sequence. Renamed the live development-facing “Phase 7 weighted
  acceptance” records to “Weighted treatment signature” without changing their frozen inputs or
  results.
- Reframed the README captures at 80% browser scale and added clickable full-resolution 2×2 grids:
  PCA/clustering/UMAP/t-SNE for exploratory structure and DESeq2/edgeR QL/limma-voom/limma for the
  shared paired-treatment model. The composites preserve exact browser pixels and scientific labels
  rather than using generated approximations.
- Phase 7 phenotype-association regression: 87 Python tests and 15 frontend integration tests passed;
  Ruff, strict mypy across 61 source files, ESLint, the Node.js 22 production build, Docker Compose
  validation, and `git diff --check` passed. The containerized R acceptance covered both GSVA and
  ssGSEA with significant positive/negative categorical effects, complete association artifacts,
  and byte-identical repeated JSON. Python exact-value tests covered categorical group effects and
  numeric slopes adjusted for a categorical covariate.
- Phase 7 cross-modality acceptance froze one eight-gene weighted signature at the same SHA-256 in
  both bundles, retained 100% mapping, recovered the prespecified positive treatment direction and
  AUROC 1.0 in each platform, and deliberately produced raw score ranges that differed by more than
  threefold. The acceptance JSON was byte-identical across repeated builds and declares raw-score
  scale comparability false.
- Cross-modality regression: 89 Python tests and 15 frontend integration tests passed; Ruff, strict
  mypy across 61 source files, ESLint, the Node.js 22 production build, both containerized
  GSVA/ssGSEA acceptance cases, JSON Schema validation, Docker Compose validation, and
  `git diff --check` passed. The existing chunk-size warning remains tracked under TD-006.
- Phase 7 public benchmark: the pinned GSE39795 RMA Expression Bundle mapped all five prespecified
  markers and all six scoring methods recovered the superficial and deep signatures in their
  expected directions with AUROC 1.0 and FDR below 0.05. The fixed policy selected mean z-score,
  its repeated score JSON was byte-identical, and the documented Make target reproduced the
  committed benchmark result byte-for-byte.
- Phase 7 completion regression: 91 combined Python tests and 15 frontend integration tests passed;
  Ruff, strict mypy across 61 source files, ESLint, the Node.js 22 production build, JSON Schema and
  Docker Compose validation, and `git diff --check` passed. The known production chunk-size warning
  remains tracked under TD-006.
- Phase 8 registry/contract regression: 96 combined Python tests and 16 frontend integration tests
  passed; Ruff, strict mypy across 62 source files, ESLint, the Node.js 22 production build, all
  versioned JSON Schemas, Docker Compose validation, and `git diff --check` passed. API tests covered
  method/result semantics, bundle-specific capability routing, resolved references, overlap floors,
  incompatible assay rejection, and the explicit pre-runner launch block. The existing production
  chunk-size warning remains tracked under TD-006.
- Phase 8 quanTIseq vertical-slice regression: 98 combined Python tests, Ruff, strict mypy across
  62 source files, ESLint, 17 frontend integration tests, the Node.js 22 production build, Docker
  Compose validation, a Nextflow DSL2 smoke run, and `git diff --check` passed. The containerized
  quanTIseq fixture passed known-mixture recovery, mapping/overlap audits, sum-to-one checks, complete
  artifact publication, and byte-identical repeated JSON.
- Phase 8 enrichment-runner regression: 100 combined Python tests, Ruff, strict mypy across 62 source
  files, ESLint, 18 frontend integration tests, the Node.js 22 production build, both Dockerfile
  checks, and a Nextflow DSL2 smoke run passed. Containerized quanTIseq, MCP-counter, and xCell
  fixtures passed expected-population recovery, overlap/semantic audits, complete artifacts, and
  byte-identical repeated JSON. The existing Vite chunk-size warning remains tracked under TD-006.
- Phase 8 cross-method comparison regression: 101 combined Python tests, Ruff, strict mypy across 62
  source files, ESLint, 18 frontend integration tests, and the Node.js 22 production build passed.
  API coverage verifies strict fraction/enrichment partitioning, exact population matching,
  reference warnings, deterministic correlations, and malformed-result exclusions. Frontend coverage
  verifies the compatible-run inventory, MCP-counter/xCell concordance, reference caveat, and
  no-comparison state. The existing Vite chunk-size warning remains tracked under TD-006.
- Phase 8 CIBERSORTx/completion regression: 103 combined Python tests and 20 frontend integration
  tests passed with Ruff, strict mypy across 62 source files, ESLint, the Node.js 22 production build,
  all versioned JSON Schemas, Docker Compose validation, and `git diff --check`. Coverage verifies
  complete provenance, immutable artifacts, exact sample identity/order, fraction composition,
  source download integrity, explicit-declaration enforcement, native-run rejection, import-form
  serialization, imported-result rendering, and comparison discovery. The existing Vite chunk-size
  warning remains tracked under TD-006.
- Phase 9 classifier-design regression: 105 combined Python tests and 22 frontend integration tests
  passed with Ruff, strict mypy across 63 source files, ESLint, the Node.js 22 production build,
  all versioned JSON Schemas, Docker Compose validation, and deterministic grouped outer/inner split
  coverage. The existing Vite chunk-size warning remains tracked under TD-006.
- Phase 9 executable classifier regression: 109 combined Python tests and 22 frontend integration
  tests passed with Ruff, strict mypy across 65 source files, ESLint, the Node.js 22 production build,
  the classifier and Result Manifest schemas, Docker Compose validation, Nextflow graph compilation,
  deterministic known-signal recovery, complete repeated OOF coverage, and the deliberate leakage
  trap. The existing Vite chunk-size warning remains tracked under TD-006.
- Phase 9 binary completion regression: 113 combined Python tests and 22 frontend integration tests
  passed with Ruff, strict mypy across 67 source files, ESLint, and the Node.js 22 production build.
  The focused classifier acceptance additionally proves deterministic bootstrap/permutation/model
  artifacts, leakage-matched tree comparisons, locked-model inference, and missing-feature rejection.
  A direct `PREDICT_WITH_MODEL` Nextflow run predicted 24 samples with complete model-feature overlap
  and published a schema-valid Result Manifest. The existing Vite chunk-size warning remains tracked
  under TD-006.
- Phase 9 multiclass and prospective-protocol regression: 120 combined Python tests and 24 frontend
  integration tests passed. Ruff and strict mypy passed across 68 API/analysis source files; ESLint,
  TypeScript, and the Node.js 22 production build passed. Direct Nextflow `RUN_ANALYSIS` and
  `PREDICT_WITH_MODEL` runs produced schema-valid multinomial results, locked models, normalized
  class probabilities for all 36 fixture samples, and Result Manifests. All differential-expression,
  signature-scoring, quanTIseq, MCP-counter, and xCell containerized R acceptance suites also passed;
  Docker Compose validation and `git diff --check` passed. The existing Vite chunk-size warning
  remains tracked under TD-006.

The development stack remains running. The large-study project is at `http://localhost:5173/projects/0694625c-23e1-4847-9622-e508ad95b895`, its prepared bundle at `http://localhost:5173/prepared-datasets/ac5bbe72-ec4e-40ec-9258-f9eae3679209`, and live results are available for PCA (`74cfc4a8-bdea-49b5-ab94-69d8534c52d6`), clustering (`2af084ac-6e90-4beb-b07c-4eabd214f066`), UMAP (`e94db15b-ab8a-4fee-ab6f-9d8e3a2ef63c`), t-SNE (`1dac23c8-5621-46bd-bb71-ddc38640647e`), DESeq2 (`e033fb5c-0516-4a74-9bf8-8e0b77d1eeaa`), limma (`2a13c140-0f8a-4617-bb59-e17b386469f9`), edgeR QL (`c31e8833-39a1-4aa8-a33b-ca87b5df90d4`), limma-voom (`339a7348-f43b-402e-be0a-555c69a0267c`), and edgeR QL with enrichment (`53509cd4-532c-4173-b505-a65e43101b6b`). The polished raw RNA-seq ingestion dashboard is at `http://localhost:5173/projects/e9574d9b-dc8f-480d-b844-64e5be0bdf31`. The public microarray project is at `http://localhost:5173/projects/32eb730d-7bda-43c1-a930-a37d91789e44`, its prepared bundle at `http://localhost:5173/prepared-datasets/75deff90-236b-4055-9c1b-e74c2ba9ec67`, and its paired limma result at `http://localhost:5173/analyses/0a800b33-6940-4b55-8928-c6c491ebe53d`.

## Next tasks

1. Add a checksum-pinned GPL570 preparation adapter, materialize GSE140494 as development-only, and prepare the GSE32646 Expression Bundle without joining its pCR/nCR truth to model predictions.
2. Fit and lock the GSE140494 model, run `PREDICT_WITH_MODEL` on GSE32646 exactly once, then evaluate the frozen primary and secondary metrics without refitting; document dataset shift and close or retain TD-018 according to the result.
3. Select an independent public deconvolution validation cohort and empirically approve method-specific overlap floors; enable EPIC only after legal review and an explicit user-supplied installation/acceptance workflow.

## Decisions and constraints

- Python supports 3.12 and newer; production containers currently pin Python 3.12.
- The frontend targets Node.js 22.13+ and patched Vite/Vitest releases; Docker is the supported path on hosts with older Node versions.
- Repository `.venv` executables are authoritative for Python checks, and the pinned worker/scientific containers are authoritative for R, Bioconductor, Node, and workflow checks; host-installed package versions must not be used as acceptance evidence.
- Scientific computation does not live in the API; the API queues frozen requests for Nextflow workers.
- Run inputs and outputs will be immutable and namespaced by internal identifiers.
- All platform output is explicitly research-use only and not clinically validated.
- Invalid user data is a successful validation computation with an `INVALID` report; infrastructure/program failures remain failed runs.
- Validation reports retain at most 100 individual findings and count suppressed findings by code to bound artifact size.
- Version 1 feature harmonization maps exact Ensembl gene identifiers and optionally strips explicit numeric version suffixes; it reports unknown identifiers instead of guessing symbol/probe mappings.

## Known blockers

- No code blocker. AWS provisioning remains intentionally deferred under TD-009 and does not block
  the local Phase 6 roadmap.

## Deferred cleanup

- Owner decisions and deferred technical/content work are maintained in `docs/debt-register.md`.
- The highest-priority implementation debt is durable object deletion/retention; uploaded run inputs
  remain immutable until the cleanup/outbox policy is implemented.

## Continue prompt

Ask Codex: **Continue implementing TranscriptForge from `docs/implementation-progress.md`.**
