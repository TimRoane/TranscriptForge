# TranscriptForge
## Codex Implementation Plan for a Nextflow-Based Human Transcriptomics Analysis Platform

## 1. Product Definition

Build **TranscriptForge**, a portfolio-grade, open-source platform for reproducible analysis of human mRNA expression data from:

1. Raw bulk RNA-seq FASTQ files.
2. Precomputed RNA-seq gene-count matrices.
3. Precomputed transcript abundance data.
4. Raw Affymetrix microarray CEL files.
5. Pre-normalized microarray or generic expression matrices.

The platform must provide a web GUI through which a user can:

- Create a project.
- Upload or register a dataset.
- Upload sample metadata.
- Validate the expression data and metadata.
- Prepare a reusable standardized expression dataset.
- Select an analysis.
- Configure analysis-specific parameters.
- Launch a Nextflow workflow.
- Monitor execution.
- Explore results interactively.
- Download tables, plots, reports, configuration, logs, and provenance.
- Re-run or clone an analysis with modified parameters.

The five primary analysis families are:

- Differential expression.
- Dimension reduction and exploratory analysis.
- Expression-based classifier development.
- RNA signature evaluation and development.
- Cell-type deconvolution.

The platform is for research and portfolio demonstration. It must not claim clinical validation or diagnostic use.

---

## 2. Core Product Decisions

### 2.1 Separate data preparation from downstream analysis

Do not rerun expensive RNA-seq quantification every time the user changes a contrast or classifier setting.

Use two run types:

1. **Dataset preparation run**
   - Converts source data into a versioned canonical Expression Bundle.
   - Performs modality-specific QC and normalization.
   - Produces reusable counts, normalized expression, feature metadata, sample metadata, and provenance.

2. **Analysis run**
   - Consumes one immutable Expression Bundle.
   - Runs one configured analysis family.
   - Produces a versioned Result Bundle.

A project can contain several datasets. A dataset can have several preparation versions. A prepared dataset can have many analysis runs.

### 2.2 Nextflow owns computation

The web application must not contain scientific analysis logic.

The GUI and API are responsible for:

- Capturing parameters.
- Validating basic form inputs.
- Creating run records.
- Writing a frozen JSON parameter file.
- Queuing a worker job.
- Launching Nextflow.
- Reading status and result manifests.
- Serving artifacts.

Nextflow processes and containerized R/Python programs are responsible for:

- Scientific validation.
- Data transformation.
- Statistical analysis.
- Machine learning.
- Plot generation.
- Report generation.
- Provenance generation.

### 2.3 Use a canonical Expression Bundle

Every prepared dataset must be converted to the same inspectable contract regardless of whether it originated from RNA-seq or microarray data.

Do not force every modality into a single numeric assay. Preserve all available assay types and let each analysis declare what it accepts.

### 2.4 Human-only scope for version 1

Version 1 supports Homo sapiens only.

Pin:

- Genome build: GRCh38.
- Gene annotation: a documented GENCODE release.
- Primary gene identifier: Ensembl gene ID without version suffix.
- Secondary identifiers: gene symbol, Entrez ID when resolvable.

Do not silently map ambiguous gene symbols. Produce mapping reports.

### 2.5 Scientific guardrails are product features

The GUI must prevent or clearly warn against invalid analysis choices.

Examples:

- DESeq2 may consume raw integer counts, not TPM.
- Limma should be used for normalized microarray data.
- RNA-seq and microarray values must not be directly concatenated without explicit harmonization.
- Batch variables should generally be included in a differential-expression design rather than blindly removed.
- Classifier feature selection and normalization must occur inside cross-validation folds.
- Replicate samples from one subject must not be split across training and test folds.
- Cell deconvolution methods return different result types; enrichment scores must not be labeled as cell fractions.
- CIBERSORTx must be treated as an optional external integration and not bundled as an unrestricted local method.

---

## 3. Recommended Technology Stack

### 3.1 Workflow and scientific execution

- Nextflow DSL2.
- Docker for local execution.
- Optional Apptainer profile for HPC.
- Optional AWS Batch profile for cloud demonstration.
- nf-test for process and workflow tests.
- MultiQC for raw RNA-seq QC aggregation.
- Quarto for final HTML reports.
- R for Bioconductor-centered statistics.
- Python for machine learning, API code, and selected visualizations.

### 3.2 Backend

- Python 3.12 or current supported stable version.
- FastAPI.
- Pydantic.
- SQLAlchemy 2.
- Alembic.
- PostgreSQL.
- Celery and Redis for durable run launching.
- boto3-compatible object-store abstraction.
- Local filesystem storage for a simple developer profile.
- MinIO for the full Docker Compose profile.
- Structured JSON logging.

### 3.3 Frontend

- React.
- TypeScript.
- Vite.
- React Router.
- TanStack Query.
- React Hook Form.
- Zod.
- Material UI or another single consistent component system.
- Plotly.js for interactive scientific plots.
- AG Grid Community or TanStack Table for large result tables.

### 3.4 Testing

- pytest for backend and Python analysis code.
- testthat for R functions.
- nf-test for Nextflow modules, subworkflows, and workflows.
- Vitest and React Testing Library for the frontend.
- Playwright for one end-to-end happy path.
- GitHub Actions for linting, unit tests, pipeline tests, image builds, and smoke tests.

---

## 4. System Architecture

```text
Browser
  |
  v
React/TypeScript GUI
  |
  v
FastAPI REST API
  |---------------------- PostgreSQL
  |---------------------- Object storage / project filesystem
  |
  v
Redis queue
  |
  v
Celery run worker
  |
  v
Nextflow launcher
  |
  +--> Local Docker
  +--> Apptainer / Slurm
  +--> AWS Batch
  |
  v
Containerized R and Python processes
  |
  v
Expression Bundles, Result Bundles, reports, logs, trace, timeline, DAG
```

The worker launches Nextflow as a subprocess with:

```bash
nextflow run pipelines/main.nf \
  -entry RUN_ANALYSIS \
  -profile docker \
  -params-file /runs/<run_id>/params.json \
  -work-dir /work/<run_id> \
  -with-trace /runs/<run_id>/provenance/trace.tsv \
  -with-report /runs/<run_id>/provenance/execution_report.html \
  -with-timeline /runs/<run_id>/provenance/timeline.html \
  -with-dag /runs/<run_id>/provenance/dag.html
```

The worker captures:

- Process ID.
- Nextflow session ID.
- Run name.
- Standard output.
- Standard error.
- `.nextflow.log`.
- Exit code.
- Start and finish timestamps.

The worker must update run state in PostgreSQL:

```text
CREATED
QUEUED
STARTING
RUNNING
SUCCEEDED
FAILED
CANCELLING
CANCELLED
```

---

## 5. Repository Structure

Create a monorepo:

```text
transcriptforge/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── .env.example
├── docker-compose.yml
├── Makefile
├── pyproject.toml
├── package.json
├── docs/
│   ├── architecture.md
│   ├── scientific-methods.md
│   ├── data-contracts.md
│   ├── local-development.md
│   ├── deployment.md
│   ├── demo-walkthrough.md
│   └── screenshots/
├── apps/
│   ├── api/
│   │   ├── transcriptforge_api/
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── db/
│   │   │   ├── models/
│   │   │   ├── schemas/
│   │   │   ├── routers/
│   │   │   ├── services/
│   │   │   ├── storage/
│   │   │   └── workers/
│   │   └── tests/
│   └── web/
│       ├── src/
│       │   ├── api/
│       │   ├── components/
│       │   ├── features/
│       │   ├── pages/
│       │   ├── plots/
│       │   ├── schemas/
│       │   └── types/
│       └── tests/
├── pipelines/
│   ├── main.nf
│   ├── nextflow.config
│   ├── nextflow_schema.json
│   ├── conf/
│   │   ├── base.config
│   │   ├── docker.config
│   │   ├── apptainer.config
│   │   ├── awsbatch.config
│   │   ├── test.config
│   │   └── resources.config
│   ├── workflows/
│   │   ├── prepare_dataset.nf
│   │   ├── run_analysis.nf
│   │   └── run_demo.nf
│   ├── subworkflows/local/
│   │   ├── ingest_matrix/
│   │   ├── prepare_rnaseq_fastq/
│   │   ├── prepare_rnaseq_counts/
│   │   ├── prepare_microarray_cel/
│   │   ├── prepare_microarray_matrix/
│   │   ├── harmonize_features/
│   │   ├── dataset_qc/
│   │   ├── differential_expression/
│   │   ├── dimension_reduction/
│   │   ├── classifier/
│   │   ├── signature_analysis/
│   │   ├── deconvolution/
│   │   └── render_report/
│   ├── modules/local/
│   │   ├── validate_manifest/
│   │   ├── fastqc/
│   │   ├── fastp/
│   │   ├── salmon_index/
│   │   ├── salmon_quant/
│   │   ├── multiqc/
│   │   ├── tximport/
│   │   ├── rma_normalize/
│   │   ├── map_gene_ids/
│   │   ├── build_expression_bundle/
│   │   ├── run_deseq2/
│   │   ├── run_edger/
│   │   ├── run_limma/
│   │   ├── run_dimension_reduction/
│   │   ├── train_classifier/
│   │   ├── evaluate_signature/
│   │   ├── run_deconvolution/
│   │   └── build_result_manifest/
│   └── tests/
│       ├── modules/
│       ├── workflows/
│       └── data/
├── analysis/
│   ├── r/
│   │   ├── R/
│   │   ├── scripts/
│   │   ├── tests/testthat/
│   │   └── renv.lock
│   └── python/
│       ├── transcriptforge_analysis/
│       ├── tests/
│       └── uv.lock
├── containers/
│   ├── rnaseq/
│   ├── r-bioconductor/
│   ├── python-ml/
│   └── reporting/
├── schemas/
│   ├── dataset_manifest.schema.json
│   ├── expression_bundle.schema.json
│   ├── analysis_request.schema.json
│   ├── result_manifest.schema.json
│   └── sample_metadata.schema.json
├── demo/
│   ├── configs/
│   ├── metadata/
│   ├── gene_sets/
│   └── expected/
└── infra/
    ├── terraform/
    └── aws/
```

---

## 6. Database Model

Implement these entities.

### Project

- id
- name
- description
- owner_id or local-user placeholder
- created_at
- updated_at

### Dataset

- id
- project_id
- name
- description
- modality
- source_kind
- organism
- genome_build
- annotation_release
- status
- created_at

### DatasetFile

- id
- dataset_id
- role
- original_name
- storage_uri
- size_bytes
- sha256
- created_at

File roles include:

- fastq_r1
- fastq_r2
- count_matrix
- abundance_file
- cel_file
- expression_matrix
- sample_metadata
- platform_manifest
- tx2gene
- gene_set

### PreparedDataset

- id
- dataset_id
- version
- preparation_run_id
- bundle_uri
- bundle_manifest_uri
- value_types_available
- sample_count
- feature_count
- qc_status
- created_at

### Analysis

- id
- project_id
- prepared_dataset_id
- analysis_type
- name
- description
- configuration_json
- created_at

### Run

- id
- run_type
- dataset_id
- prepared_dataset_id
- analysis_id
- state
- profile
- params_uri
- output_uri
- work_uri
- nextflow_session_id
- nextflow_run_name
- exit_code
- error_summary
- started_at
- finished_at
- created_at

### Artifact

- id
- run_id
- artifact_type
- title
- relative_path
- storage_uri
- mime_type
- size_bytes
- sha256
- display_order
- metadata_json

### ModelRecord

- id
- analysis_id
- run_id
- model_name
- algorithm
- outcome_column
- model_uri
- model_card_uri
- metrics_json
- feature_count
- created_at

---

## 7. Canonical Dataset Manifest

Before preparation, write a `dataset_manifest.json`.

Example:

```json
{
  "schema_version": "1.0.0",
  "dataset_id": "ds_123",
  "name": "Airway dexamethasone study",
  "organism": "Homo sapiens",
  "modality": "bulk_rnaseq",
  "source_kind": "count_matrix",
  "genome_build": "GRCh38",
  "annotation_release": "GENCODE_XX",
  "feature_id_type": "ensembl_gene_id",
  "value_type": "raw_counts",
  "matrix_orientation": "features_by_samples",
  "matrix_file": "inputs/counts.tsv.gz",
  "sample_metadata_file": "inputs/sample_metadata.tsv",
  "sample_id_column": "sample_id",
  "feature_id_column": "gene_id",
  "paired_end": null,
  "strandedness": null,
  "created_by": "transcriptforge",
  "checksums": {}
}
```

Supported modality and source combinations:

```text
bulk_rnaseq + fastq
bulk_rnaseq + count_matrix
bulk_rnaseq + salmon_quant
microarray + affymetrix_cel
microarray + normalized_matrix
generic_expression + normalized_matrix
```

Do not initially claim universal raw microarray support. Version 1 raw-file support is specifically Affymetrix CEL. Add Illumina and Agilent through explicit adapters later.

---

## 8. Canonical Expression Bundle

Every preparation workflow must emit:

```text
expression_bundle/
├── bundle_manifest.json
├── sample_metadata.tsv
├── feature_metadata.tsv
├── assays/
│   ├── raw_counts.tsv.gz
│   ├── normalized_expression.tsv.gz
│   ├── log_expression.tsv.gz
│   ├── tpm.tsv.gz
│   └── transcript_abundance.tsv.gz
├── qc/
│   ├── qc_metrics.tsv
│   ├── sample_flags.tsv
│   ├── plots/
│   └── multiqc/
├── mappings/
│   ├── feature_mapping.tsv
│   ├── unmapped_features.tsv
│   └── duplicate_resolution.tsv
├── provenance/
│   ├── input_checksums.tsv
│   ├── software_versions.yml
│   ├── parameters.json
│   └── session_info.txt
└── preview/
    ├── samples.json
    ├── features.json
    └── available_analyses.json
```

Not every assay file must exist. `bundle_manifest.json` declares what is available.

Example assay declaration:

```json
{
  "assays": [
    {
      "name": "raw_counts",
      "path": "assays/raw_counts.tsv.gz",
      "value_type": "nonnegative_integer",
      "scale": "linear",
      "feature_level": "gene",
      "recommended_for": ["differential_expression"]
    },
    {
      "name": "log_expression",
      "path": "assays/log_expression.tsv.gz",
      "value_type": "continuous",
      "scale": "log2",
      "feature_level": "gene",
      "recommended_for": [
        "dimension_reduction",
        "classifier",
        "signature_analysis",
        "deconvolution"
      ]
    }
  ]
}
```

`feature_metadata.tsv` must include:

- feature_id
- ensembl_gene_id
- gene_symbol
- entrez_id
- gene_name
- gene_biotype
- chromosome
- start
- end
- mapping_status
- original_feature_id

`sample_metadata.tsv` must include:

- sample_id

It may include:

- subject_id
- condition
- batch
- sex
- age
- tissue
- collection_site
- outcome
- timepoint
- platform
- cohort

Preserve all user metadata columns.

---

## 9. Dataset Preparation Workflows

## 9.1 Raw RNA-seq FASTQ

Default path:

```text
FASTQ
 -> validate sample sheet
 -> FastQC
 -> fastp
 -> Salmon quantification
 -> tximport
 -> gene-level counts and TPM
 -> MultiQC
 -> feature harmonization
 -> dataset-level QC
 -> Expression Bundle
```

Requirements:

- Support single-end and paired-end reads.
- Support multiple lanes per biological sample.
- Validate that all referenced files exist.
- Validate that sample IDs are unique.
- Merge lanes at the logical sample level.
- Allow user-selected or auto-detected strandedness.
- Pin a GRCh38/GENCODE reference bundle.
- Build or download a versioned Salmon index.
- Cache the index outside individual run directories.
- Record reference checksums and versions.
- Preserve transcript-level abundance.
- Produce gene-level counts using tximport.
- Add a later optional STAR plus featureCounts path, but do not block the MVP on it.

RNA-seq QC metrics should include:

- Read count.
- Read length.
- Adapter content.
- Quality scores.
- Duplication estimate.
- Mapping or assignment rate.
- Number and percentage of detected genes.
- Library size.
- Mitochondrial expression percentage when identifiers permit.
- Ribosomal expression percentage when identifiers permit.
- Sample-to-sample correlation.
- PCA outlier indicators.

Do not automatically discard samples. Flag them and let the user create a derived prepared-dataset version excluding selected samples.

## 9.2 RNA-seq count matrix

Validation:

- Detect or require matrix orientation.
- Confirm numeric values.
- Confirm nonnegative values.
- Confirm integer-like values for raw counts.
- Detect duplicated sample IDs.
- Detect duplicated feature IDs.
- Ensure sample metadata IDs match matrix columns exactly.
- Report metadata-only and matrix-only samples.
- Remove Ensembl version suffixes only when explicitly configured.
- Map identifiers to the pinned human annotation.
- Preserve the original feature IDs.
- Aggregate duplicate mappings using sum for count assays.
- Produce a complete mapping report.

Normalization and derived assays:

- Preserve raw counts unchanged.
- Produce DESeq2 variance-stabilizing or regularized-log-style exploratory assay based on sample size and configured method.
- Produce log2 CPM for visualization and machine-learning use.
- Produce TPM only when valid gene-length information is available. Do not invent TPM from counts without lengths.

## 9.3 Salmon abundance import

Support a sample sheet pointing to per-sample `quant.sf` files.

- Validate consistent transcript annotation.
- Import transcript abundance.
- Use a pinned transcript-to-gene map.
- Generate gene counts, gene TPM, and transcript abundance.
- Retain mapping and summarization provenance.

## 9.4 Raw Affymetrix CEL

Default path:

```text
CEL files
 -> identify/validate platform
 -> read with oligo
 -> array QC
 -> RMA background correction, normalization, summarization
 -> probe annotation
 -> probe-to-gene aggregation
 -> feature harmonization
 -> Expression Bundle
```

Requirements:

- Start with one or two explicitly supported Affymetrix platforms used by the demonstration datasets.
- Implement an adapter registry so more platforms can be added.
- Never guess an annotation package without recording confidence and allowing override.
- Preserve probe-level normalized expression.
- Produce gene-level summarized expression.
- Offer probe aggregation methods:
  - highest median absolute deviation probe
  - median across probes
  - mean across probes
- Default to the highest-variability representative probe and clearly document the choice.
- Output array intensity distributions, boxplots, PCA, sample correlations, and available array-QC metrics.

## 9.5 Normalized microarray or generic matrix

Require the user to specify:

- Feature identifier type.
- Whether values are already log transformed.
- Platform, if known.
- Matrix orientation.
- Missing-value handling.
- Whether values have already been normalized.

Validation:

- Numeric and finite-value checks.
- Distribution plot to detect likely linear versus log scale.
- Duplicate features and samples.
- Metadata alignment.
- Missingness by sample and feature.
- Feature mapping rate.

Do not automatically quantile-normalize a matrix that the user declares normalized. Allow an explicit optional transform and record it.

---

## 10. Shared Dataset QC

Every prepared dataset must receive a shared QC module.

Outputs:

- Sample summary table.
- Feature summary table.
- Expression distribution plots.
- Library-size or total-signal plot.
- Detected-feature plot.
- Sample correlation heatmap.
- Hierarchical sample dendrogram.
- PCA plot.
- Top variable gene heatmap.
- Missingness plot.
- Metadata association overview.
- Potential outlier table.
- Potential confounding table.
- QC report HTML.

Outlier logic must be transparent and conservative:

- Robust z-score on library size or total signal.
- Robust z-score on detected features.
- Median sample-to-sample correlation.
- PCA distance using a robust covariance approach when feasible.
- Never automatically label a sample “bad.”
- Use statuses such as `PASS`, `REVIEW`, and `SEVERE_REVIEW`.

Create `available_analyses.json` based on assay availability.

Example:

```json
{
  "differential_expression": {
    "available": true,
    "methods": ["deseq2", "edger_ql", "limma_voom"]
  },
  "cell_deconvolution": {
    "available": true,
    "methods": ["epic", "quantiseq", "mcp_counter", "xcell"],
    "warnings": []
  }
}
```

---

## 11. Differential Expression Module

## 11.1 GUI inputs

- Prepared dataset.
- Assay.
- Method.
- Design formula.
- Primary variable.
- Contrast.
- Optional covariates.
- Optional subject/block column.
- Reference levels.
- Low-expression filtering.
- FDR threshold.
- Absolute log2-fold-change threshold.
- Optional independent filtering.
- Optional fold-change shrinkage.
- Number of genes in heatmap.
- Optional pathway-enrichment settings.

Provide a visual design builder, but always show the generated formula.

Examples:

```text
~ condition
~ batch + condition
~ sex + age + batch + condition
~ subject_id + timepoint
~ treatment * timepoint
```

Before launch:

- Build the model matrix.
- Detect rank deficiency.
- Detect variables with one level.
- Detect empty contrast groups.
- Show sample counts per design cell.
- Warn about severe imbalance.
- Require replicates for inferential analysis.
- Display the exact contrast in plain English.

## 11.2 Method routing

- Raw RNA-seq counts:
  - DESeq2 default.
  - edgeR quasi-likelihood optional.
  - limma-voom optional.
- Normalized log-scale microarray:
  - limma default.
- Generic continuous log expression:
  - limma if assumptions are valid.
- Reject DESeq2 for TPM, CPM, or normalized microarray values.

## 11.3 Outputs

- Complete gene-level statistics table.
- Significant results table.
- MA plot.
- Volcano plot.
- P-value histogram.
- Adjusted-p-value histogram.
- Effect-size distribution.
- Top-gene heatmap.
- Sample distance plot.
- Per-gene expression plots for selected genes.
- Normalized expression table for plotted genes.
- Design matrix.
- Contrast definition.
- Method diagnostics.
- Optional enrichment:
  - ranked-list enrichment
  - over-representation analysis
- Quarto HTML report.
- Result manifest.

Gene table columns should include:

- feature_id
- gene_symbol
- base_expression
- log2_fold_change
- shrunken_log2_fold_change when available
- standard_error
- statistic
- p_value
- adjusted_p_value
- significant
- contrast
- method

Interactive GUI requirements:

- Filter by FDR and fold change.
- Search by gene symbol or ID.
- Click a volcano point to open a gene detail panel.
- Download the filtered or full table.
- Save selected genes as a new signature.

---

## 12. Dimension Reduction and Exploratory Module

Methods:

- PCA.
- UMAP.
- t-SNE.
- Hierarchical clustering.

Inputs:

- Assay.
- Feature filter.
- Number of most-variable genes.
- Centering.
- Scaling.
- Distance metric.
- Number of components.
- Random seed.
- UMAP neighbors and minimum distance.
- t-SNE perplexity.
- Metadata color, shape, label, and facet columns.

Defaults:

- Use log or variance-stabilized expression.
- Remove invariant features.
- Select top variable genes.
- Center features.
- Do not scale each gene to unit variance by default for every mode; make the choice explicit.
- Fix and record random seeds.

Outputs:

- Interactive score plots.
- Static SVG/PNG plots.
- Explained-variance plot for PCA.
- PCA loadings.
- Top positive and negative loading genes.
- UMAP and t-SNE coordinates.
- Hierarchical dendrogram.
- Sample correlation heatmap.
- Cluster assignments when the user requests clustering.
- Coordinates table suitable for download.
- Analysis report.

Batch-correction option:

- Offer “visualization-only adjustment.”
- Preserve the original assay.
- Make the adjusted assay a derived artifact.
- Require the user to specify biological variables to preserve.
- Label all adjusted plots clearly.
- Do not use visualization-only adjusted values for differential expression.

---

## 13. Expression-Based Classifier Development

This module is the most important place to demonstrate statistical maturity.

## 13.1 Supported tasks

Version 1:

- Binary classification.
- Multiclass classification.

Later:

- Continuous regression.
- Time-to-event modeling.

## 13.2 GUI inputs

- Outcome column.
- Positive class for binary outcomes.
- Subject/group column.
- Cohort/site column.
- Optional external test dataset.
- Assay.
- Feature filtering method.
- Number of top variable genes.
- Optional candidate gene list.
- Algorithms.
- Class-weighting choice.
- Cross-validation strategy.
- Number of folds and repeats.
- Random seed.
- Primary metric.
- Probability calibration option.
- Decision-threshold strategy.
- Model interpretation options.

## 13.3 Algorithms

Primary baseline:

- Elastic-net logistic regression.

Optional comparisons:

- Random forest.
- Gradient-boosted trees.
- Linear support-vector machine with calibrated probabilities.

Do not lead with deep learning. Typical transcriptomic cohorts are high-dimensional and often too small for a convincing deep-learning portfolio result.

## 13.4 Leakage prevention

Implement preprocessing as a fitted pipeline.

Inside each training fold:

1. Remove features failing the training-fold filter.
2. Impute missing values if allowed.
3. Fit transformation or standardization on training data only.
4. Select features using training data only.
5. Tune hyperparameters using inner cross-validation.
6. Fit the final fold model.
7. Apply the fitted preprocessing and model to the untouched outer test fold.

Never:

- Select genes using the full dataset before cross-validation.
- Normalize train and test together when normalization learns sample-level parameters.
- Split repeated samples from the same patient across folds.
- Tune a probability threshold on the final test set.
- Report the best of many algorithms without preserving the selection process.

## 13.5 Validation modes

Mode A: External validation supplied

- Train and tune only on the development dataset.
- Lock preprocessing, features, model, and threshold.
- Evaluate once on the external dataset.
- Report platform/cohort differences.

Mode B: No external dataset

- Use repeated nested stratified cross-validation.
- Use group-aware splitting when `subject_id`, site, or cohort is provided.
- Aggregate out-of-fold predictions.
- Clearly label performance as internal validation.

Mode C: Predefined train/test column

- Honor the split.
- Validate that no group crosses partitions.
- Use training data only for all tuning.

## 13.6 Metrics

Binary:

- ROC-AUC.
- PR-AUC.
- Balanced accuracy.
- Accuracy.
- Sensitivity.
- Specificity.
- Precision.
- Recall.
- F1.
- MCC.
- Brier score.
- Calibration intercept and slope when feasible.
- Confusion matrix at the locked threshold.

Multiclass:

- Macro and weighted ROC-AUC where valid.
- Macro and weighted F1.
- Balanced accuracy.
- Per-class sensitivity and precision.
- Confusion matrix.
- One-vs-rest curves.

Use bootstrap confidence intervals on pooled out-of-fold or external predictions where appropriate.

## 13.7 Negative and robustness controls

Add:

- Permuted-label baseline.
- Learning curve.
- Feature stability across folds.
- Performance by batch, cohort, sex, or other selected metadata strata.
- Prediction distribution by class.
- Calibration plot.
- Decision-curve analysis as an optional advanced feature.
- Sensitivity analysis with and without flagged QC samples.

## 13.8 Outputs

- Out-of-fold predictions.
- External predictions if provided.
- Model comparison table.
- ROC and precision-recall plots.
- Calibration plot.
- Confusion matrix.
- Learning curve.
- Feature stability table.
- Coefficient or feature-importance plots.
- Selected-feature matrix.
- Frozen preprocessing and model object.
- Feature schema.
- Model card.
- Inference example.
- Complete configuration and random seeds.

Model card sections:

- Intended research use.
- Data used.
- Outcome definition.
- Cohort composition.
- Preprocessing.
- Validation strategy.
- Performance with uncertainty.
- Selected features.
- Known limitations.
- Platform limitations.
- Non-clinical disclaimer.

Add a future `PREDICT_WITH_MODEL` Nextflow entry workflow that validates a new expression bundle against the model’s feature schema and produces predictions.

---

## 14. RNA Signature Module

Separate two concepts.

### 14.1 Signature evaluation

Evaluate an existing gene set or weighted gene signature.

Inputs:

- Gene list, weighted gene list, or GMT file.
- Assay.
- Gene identifier type.
- Scoring method.
- Optional phenotype/outcome.
- Optional covariates.
- Optional group/block column.

Scoring methods:

- Mean expression.
- Mean z-score.
- Weighted linear score.
- ssGSEA/GSVA-style score.
- Rank-based single-sample score.

Outputs:

- Per-sample scores.
- Mapping coverage.
- Missing signature genes.
- Score distributions.
- Group comparison.
- Correlation with numeric metadata.
- ROC/PR analysis for binary outcomes.
- Heatmap of signature genes.
- Score-versus-phenotype plot.
- Report.

Never hide poor mapping. Show:

- Number of requested genes.
- Number mapped.
- Number duplicated.
- Number missing.
- Final genes used.

### 14.2 Signature development

This is a specialized classifier workflow, not a shortcut around validation.

Allow:

- Candidate genes from a differential-expression result.
- Candidate genes uploaded by the user.
- Elastic-net feature selection.
- Maximum signature size.
- Stability threshold.
- Locked scoring formula.

All feature selection remains inside nested cross-validation.

Outputs:

- Candidate-gene provenance.
- Stability plot.
- Final signature formula.
- Coefficients.
- Internal or external validation.
- Model card.
- A simple score calculator.

The GUI should allow a user to send significant genes from a differential-expression run into a new signature-development draft while warning that this does not constitute independent validation.

---

## 15. Cell-Type Deconvolution Module

Version 1 methods:

- EPIC.
- quanTIseq.
- MCP-counter.
- xCell.

Optional:

- ESTIMATE.
- User-supplied signature matrix with an open deconvolution implementation.
- CIBERSORTx external adapter.

Do not bundle CIBERSORTx credentials, proprietary resources, or automated terms acceptance.

## 15.1 Method metadata registry

Create a registry that declares for every method:

- Accepted input scale.
- Required identifier type.
- Whether linear-scale values are required.
- Whether the output is a fraction, absolute score, or enrichment score.
- Supported tissue assumptions.
- Citation.
- License notes.
- Whether internet access or credentials are required.

## 15.2 Input validation

- Confirm adequate human gene-symbol mapping.
- Confirm no negative values for methods that prohibit them.
- Confirm expected scale.
- Require explicit confirmation before transforming data.
- Report gene-overlap percentage with the method signature.
- Reject methods below a configurable minimum overlap.

## 15.3 Outputs

- Cell-type estimate matrix.
- Method metadata.
- Mapping report.
- Stacked-bar plot only for methods producing compositional fractions.
- Heatmap.
- Per-cell-type boxplots by phenotype.
- Association tests using configurable covariates.
- Correlation between cell estimates and signatures.
- Cross-method comparison when multiple methods are selected.
- Result report.

Clearly label:

- Fractions.
- Relative fractions.
- Absolute scores.
- Enrichment scores.

Do not force unlike outputs onto one common percentage scale.

---

## 16. Cross-Platform and Multi-Cohort Analysis

Do not make direct RNA-seq/microarray integration part of the first MVP.

Add it after single-dataset analyses are stable.

Version 2 capabilities:

- Intersect datasets by Ensembl gene ID.
- Create within-dataset standardized expression.
- Preserve platform and cohort columns.
- Optional ComBat-style harmonization for exploratory purposes.
- Leave-one-cohort-out validation.
- Train on one cohort and externally validate on another.
- Meta-analysis of differential-expression effects rather than naïve matrix merging.
- Forest plots of cohort-specific effects.
- Platform-aware signature validation.

The preferred portfolio demonstration is:

- Develop a classifier or signature in one cohort.
- Lock it.
- Validate it in a second cohort measured on another platform.
- Discuss loss of performance and domain shift honestly.

---

## 17. Result Bundle Contract

Every analysis workflow emits:

```text
result_bundle/
├── result_manifest.json
├── summary.json
├── tables/
├── plots/
│   ├── interactive/
│   └── static/
├── models/
├── report/
│   └── report.html
├── provenance/
│   ├── parameters.json
│   ├── software_versions.yml
│   ├── session_info.txt
│   ├── trace.tsv
│   ├── execution_report.html
│   ├── timeline.html
│   └── dag.html
└── logs/
```

`result_manifest.json` drives the GUI.

Example:

```json
{
  "schema_version": "1.0.0",
  "analysis_type": "differential_expression",
  "title": "Treated versus control",
  "summary_metrics": [
    {"label": "Samples", "value": 24},
    {"label": "Significant genes", "value": 418},
    {"label": "FDR threshold", "value": 0.05}
  ],
  "sections": [
    {
      "id": "overview",
      "title": "Overview",
      "items": [
        {
          "type": "plotly_json",
          "title": "Volcano plot",
          "path": "plots/interactive/volcano.json"
        },
        {
          "type": "table",
          "title": "Differential expression results",
          "path": "tables/differential_expression.tsv.gz"
        }
      ]
    }
  ],
  "downloads": [],
  "warnings": []
}
```

The frontend must render generic sections and items from this manifest. Avoid hard-coding every possible output page.

---

## 18. API Endpoints

Implement REST endpoints.

### Projects

```text
POST   /api/projects
GET    /api/projects
GET    /api/projects/{project_id}
PATCH  /api/projects/{project_id}
DELETE /api/projects/{project_id}
```

### Datasets

```text
POST   /api/projects/{project_id}/datasets
POST   /api/datasets/{dataset_id}/files
GET    /api/datasets/{dataset_id}
POST   /api/datasets/{dataset_id}/validate
POST   /api/datasets/{dataset_id}/prepare
GET    /api/datasets/{dataset_id}/prepared-versions
```

### Analyses

```text
POST   /api/prepared-datasets/{prepared_id}/analyses
GET    /api/analyses/{analysis_id}
POST   /api/analyses/{analysis_id}/run
POST   /api/analyses/{analysis_id}/clone
```

### Runs

```text
GET    /api/runs/{run_id}
GET    /api/runs/{run_id}/events
POST   /api/runs/{run_id}/cancel
GET    /api/runs/{run_id}/artifacts
GET    /api/runs/{run_id}/result-manifest
GET    /api/runs/{run_id}/logs
```

Use server-sent events or short polling for run status. Do not stream raw Nextflow logs continuously unless requested by the UI.

### Models

```text
GET    /api/models
GET    /api/models/{model_id}
POST   /api/models/{model_id}/predict
```

Prediction may initially launch a Nextflow inference workflow rather than run directly in the API.

---

## 19. GUI Pages

## 19.1 Dashboard

Show:

- Projects.
- Recent datasets.
- Recent runs.
- Run state counts.
- Recent models.
- Demo-project shortcut.

## 19.2 Project page

Tabs:

- Overview.
- Datasets.
- Analyses.
- Models.
- Activity.

## 19.3 New dataset wizard

Steps:

1. Name and modality.
2. Source type.
3. Upload/register files.
4. Upload metadata.
5. Map columns.
6. Configure identifiers and platform.
7. Preview.
8. Validate.
9. Prepare.

Show validation errors inline with downloadable details.

## 19.4 Prepared dataset page

Tabs:

- Overview.
- Samples.
- Features.
- Assays.
- QC.
- Provenance.
- New analysis.

Allow:

- Search samples and features.
- View excluded/flagged samples.
- Create a derived dataset version with selected exclusions.
- Download the bundle manifest.

## 19.5 New analysis wizard

First choose:

- Differential expression.
- Dimension reduction.
- Classifier.
- Signature.
- Deconvolution.

The form must be generated from a typed analysis schema plus custom components for design formulas, contrasts, and gene sets.

Before launch, show a review page:

- Dataset version.
- Assay.
- Method.
- Sample count.
- Included/excluded samples.
- Key parameters.
- Warnings.
- Estimated resource class.
- Frozen JSON configuration.

## 19.6 Run page

Show:

- State.
- Elapsed time.
- Current or recent processes.
- Completed/failed process counts.
- Resource summary when available.
- Condensed log.
- Cancel button.
- Links to trace, report, timeline, and DAG after completion.

## 19.7 Results page

Render `result_manifest.json`.

Common controls:

- Download report.
- Download all results.
- Clone analysis.
- View parameters.
- View provenance.
- Open log.
- Compare with another run.

Analysis-specific interactive components may enrich the generic renderer but must not replace the manifest contract.

## 19.8 Model registry

Show:

- Model name.
- Outcome.
- Algorithm.
- Validation type.
- Primary metric.
- Feature count.
- Dataset/cohort.
- Created date.
- Research-use disclaimer.

---

## 20. Nextflow Design

Use DSL2 modules and named workflows.

Top-level entries:

```text
PREPARE_DATASET
RUN_ANALYSIS
RUN_DEMO
PREDICT_WITH_MODEL
```

`PREPARE_DATASET` routes by source type.

Pseudo-structure:

```groovy
workflow PREPARE_DATASET {
    VALIDATE_DATASET_MANIFEST(params.dataset_manifest)

    if (params.source_kind == 'fastq') {
        PREPARE_RNASEQ_FASTQ(...)
    } else if (params.source_kind == 'count_matrix') {
        PREPARE_RNASEQ_COUNTS(...)
    } else if (params.source_kind == 'salmon_quant') {
        PREPARE_SALMON_QUANT(...)
    } else if (params.source_kind == 'affymetrix_cel') {
        PREPARE_MICROARRAY_CEL(...)
    } else if (params.source_kind == 'normalized_matrix') {
        PREPARE_EXPRESSION_MATRIX(...)
    } else {
        error "Unsupported source kind"
    }

    DATASET_QC(...)
    BUILD_EXPRESSION_BUNDLE(...)
}
```

`RUN_ANALYSIS` routes by analysis type:

```groovy
workflow RUN_ANALYSIS {
    VALIDATE_EXPRESSION_BUNDLE(params.expression_bundle)
    VALIDATE_ANALYSIS_REQUEST(params.analysis_request)

    if (params.analysis_type == 'differential_expression') {
        DIFFERENTIAL_EXPRESSION(...)
    } else if (params.analysis_type == 'dimension_reduction') {
        DIMENSION_REDUCTION(...)
    } else if (params.analysis_type == 'classifier') {
        CLASSIFIER(...)
    } else if (params.analysis_type == 'signature') {
        SIGNATURE_ANALYSIS(...)
    } else if (params.analysis_type == 'deconvolution') {
        DECONVOLUTION(...)
    } else {
        error "Unsupported analysis type"
    }

    BUILD_RESULT_MANIFEST(...)
    RENDER_REPORT(...)
}
```

Requirements:

- Keep channel wiring in workflows.
- Keep one tool or cohesive operation per process.
- Give every process a container.
- Use labels for resource classes.
- Configure resources in config files rather than embedding environment-specific values.
- Pin image digests or immutable tags.
- Emit tool versions.
- Use retry behavior only for infrastructure-like failures.
- Use `errorStrategy` carefully; scientific failures must not be silently ignored.
- Support `-resume`.
- Use deterministic seeds.
- Use schema validation before expensive work.
- Make published outputs immutable per run ID.

Resource labels:

```text
process_low
process_medium
process_high
process_high_memory
process_r
process_python_ml
```

---

## 21. Analysis Program Design

Do not write each R analysis as one untestable script.

Create reusable package-style functions.

Example R functions:

```text
read_expression_bundle()
validate_expression_bundle()
build_summarized_experiment()
validate_design_formula()
run_deseq2_analysis()
run_edger_ql_analysis()
run_limma_analysis()
run_pca()
run_signature_scoring()
run_deconvolution_method()
write_plotly_spec()
write_result_manifest_fragment()
```

Example Python functions:

```text
load_expression_bundle()
validate_classification_request()
build_group_aware_splits()
build_feature_pipeline()
run_nested_cross_validation()
fit_locked_model()
evaluate_predictions()
bootstrap_metrics()
calculate_feature_stability()
write_model_card()
write_result_manifest_fragment()
```

CLI scripts should be thin wrappers around tested functions.

Every command-line program must:

- Accept an input JSON configuration.
- Validate it.
- Log structured progress.
- Exit nonzero on failure.
- Write an `error.json` with an actionable message when feasible.
- Write outputs atomically.
- Write a `versions.yml`.

---

## 22. Container Strategy

Use several purpose-built images instead of one enormous image.

### `transcriptforge-rnaseq`

- fastp
- FastQC
- Salmon
- MultiQC
- required utilities

### `transcriptforge-r-bioconductor`

- R
- Bioconductor
- DESeq2
- edgeR
- limma
- oligo
- tximport
- GSVA or chosen signature packages
- deconvolution packages
- plotting/report dependencies

### `transcriptforge-python-ml`

- Python
- pandas
- numpy
- scipy
- scikit-learn
- xgboost
- pyarrow
- joblib
- matplotlib
- plotly
- pydantic

### `transcriptforge-reporting`

- Quarto
- R/Python engines required for report rendering

Use lock files and record container digests.

---

## 23. Testing Strategy

## 23.1 Schema tests

Test:

- Valid manifests.
- Missing required fields.
- Unsupported source combinations.
- Invalid identifier type.
- Invalid analysis/assay combination.
- Invalid contrast.
- Duplicate sample IDs.
- Mismatched metadata.

## 23.2 Scientific unit tests

Create small deterministic fixtures.

Examples:

- Count matrix with a known induced group effect.
- Matrix with duplicated Ensembl IDs.
- Matrix with missing sample metadata.
- Paired design.
- Rank-deficient design.
- Classifier data with grouped repeated samples.
- Deliberate leakage trap.
- Signature with partial mapping.
- Deconvolution output-type tests.

Assert:

- Correct routing.
- Correct input rejection.
- Stable output schemas.
- Expected direction of effects.
- No group overlap in cross-validation.
- Feature selection is fitted independently per fold.
- Reproducible metrics for fixed seeds.

## 23.3 Nextflow tests

For every module:

- Successful execution.
- Expected files.
- Expected file content patterns.
- Version output.
- Failure on invalid inputs.

For each top-level workflow:

- Minimal test dataset.
- Snapshot or checksum selected deterministic outputs.
- Validate bundle and result manifests.

## 23.4 API tests

- CRUD.
- Upload metadata.
- Validation.
- Run creation.
- Worker state transitions.
- Cancellation.
- Artifact authorization/path safety.
- Result-manifest serving.

## 23.5 Frontend tests

- Dataset wizard.
- Analysis wizard.
- Contrast builder.
- Run status.
- Result-manifest renderer.
- Error display.

## 23.6 End-to-end test

One Playwright test:

1. Open demo project.
2. Select a prepared count dataset.
3. Launch PCA.
4. Wait for completion in a test profile.
5. Verify the PCA result page renders.
6. Download coordinates.

---

## 24. Demonstration Datasets

Ship three demo experiences.

### Demo 1: Small RNA-seq count dataset

Purpose:

- Fast local execution.
- Differential expression.
- PCA.
- Signature scoring.

Characteristics:

- Human.
- Small sample count.
- Clear treatment or condition variable.
- Stored as a compact matrix and metadata.

### Demo 2: Tiny raw RNA-seq FASTQ dataset

Purpose:

- Demonstrate full Nextflow processing.
- FastQC, trimming, Salmon, tximport, MultiQC.
- Use intentionally tiny reads suitable for CI.
- Clearly label it as a technical test dataset, not a biologically meaningful study.

### Demo 3: Microarray disease cohort

Purpose:

- Raw or prepared Affymetrix workflow.
- Classifier development.
- Signature evaluation.
- External or cohort-aware validation when possible.

Do not redistribute data without checking source terms. Prefer download scripts and documented public accession identifiers for larger datasets.

Create a polished default demo project populated by a seed command:

```bash
make seed-demo
```

---

## 25. Portfolio Narrative

The README must explain that TranscriptForge demonstrates:

- Nextflow DSL2 workflow engineering.
- Containerized reproducible bioinformatics.
- RNA-seq and microarray domain knowledge.
- Statistical design and differential expression.
- High-dimensional machine-learning validation.
- Data contracts.
- API and React product engineering.
- Run orchestration.
- Cloud-portable execution.
- Scientific provenance.
- Testing and CI.

Include screenshots or a short animated walkthrough showing:

1. Dataset upload and validation.
2. QC dashboard.
3. Differential-expression design builder.
4. Running Nextflow job.
5. Volcano and gene-detail interaction.
6. Classifier validation and feature stability.
7. Model card.
8. Nextflow DAG and execution report.

---

## 26. Phased Implementation Plan

## Phase 0: Repository and architecture foundation

Tasks:

- Create monorepo.
- Add licenses and contribution files.
- Configure Python, TypeScript, R, and Nextflow formatting/linting.
- Create Docker Compose with PostgreSQL, Redis, MinIO, API, worker, and web.
- Create architecture and data-contract docs.
- Add GitHub Actions skeleton.
- Add Makefile commands.

Commands:

```text
make dev
make stop
make test
make lint
make pipeline-test
make seed-demo
```

Acceptance criteria:

- `docker compose up` launches all services.
- API health endpoint succeeds.
- Web app loads.
- Worker can consume a test queue task.
- CI runs placeholder checks.

## Phase 1: Core database, storage, and project GUI

Tasks:

- Implement database models and migrations.
- Implement project and dataset CRUD.
- Implement safe file upload.
- Calculate file SHA-256.
- Add local and S3-compatible storage adapters.
- Build dashboard, project page, and dataset wizard shell.
- Add typed API client.

Acceptance criteria:

- A user can create a project and dataset.
- A user can upload a matrix and metadata.
- Files survive service restart.
- File paths cannot escape the project namespace.
- Uploaded-file metadata and checksums are stored.

## Phase 2: Schemas and matrix ingestion

Tasks:

- Implement JSON schemas.
- Build matrix and metadata validators.
- Implement matrix orientation preview.
- Implement ID-column mapping.
- Implement `PREPARE_DATASET` for count matrices and normalized matrices.
- Implement feature mapping.
- Build Expression Bundle.
- Implement shared dataset QC.
- Render prepared-dataset page.

Acceptance criteria:

- A valid count matrix becomes an Expression Bundle.
- An invalid matrix produces actionable errors.
- Original counts remain unchanged.
- Mapping coverage and duplicates are reported.
- QC plots render in the GUI.
- Bundle manifest validates against its schema.

## Phase 3: Dimension reduction

Tasks:

- Implement PCA first.
- Add hierarchical clustering.
- Add UMAP.
- Add t-SNE.
- Create result manifest.
- Create generic results renderer.
- Add Quarto report.

Acceptance criteria:

- User launches PCA from GUI.
- Worker launches Nextflow.
- Run state updates correctly.
- Result page shows interactive PCA and variance plot.
- Coordinates and loadings are downloadable.
- Re-running with the same seed produces the same coordinates where the algorithm permits.

This phase is the first complete vertical slice and should be made polished before adding more science.

## Phase 4: Differential expression

Tasks:

- Build design formula and contrast UI.
- Implement server-side and R-side design validation.
- Implement DESeq2.
- Implement limma.
- Add edgeR QL and limma-voom after the first two work.
- Add volcano, MA, heatmap, gene detail, and tables.
- Add optional enrichment.
- Add “save selected genes as signature.”

Acceptance criteria:

- Correct method is selected by assay.
- Invalid method/assay combinations are blocked.
- Rank-deficient designs are rejected before expensive analysis.
- Results table and plots are internally consistent.
- Report contains design, contrast, thresholds, and session information.

## Phase 5: Raw RNA-seq

Tasks:

- Implement sample-sheet ingestion.
- Add FastQC, fastp, Salmon, tximport, and MultiQC modules.
- Create a pinned reference bundle configuration.
- Cache Salmon index.
- Support paired and single-end reads.
- Add local Docker test.
- Add AWS Batch profile after local execution is reliable.

Acceptance criteria:

- Tiny FASTQ demo runs end to end.
- Gene counts and TPM enter an Expression Bundle.
- MultiQC is linked in the GUI.
- Reference and tool versions are recorded.
- `-resume` avoids recomputing completed tasks.

## Phase 6: Raw Affymetrix microarray

Tasks:

- Select the first supported Affymetrix platform.
- Implement CEL platform validation.
- Implement RMA with `oligo`.
- Add probe annotation and aggregation.
- Add array-specific QC.
- Create platform adapter interface.
- Add a documented public demo download script.

Acceptance criteria:

- Supported CEL files produce probe- and gene-level assays.
- Unsupported arrays fail with an explicit platform message.
- Probe mapping and aggregation are fully documented.
- Limma differential expression works on the resulting bundle.

## Phase 7: Signature analysis

Tasks:

- Implement gene-list and GMT upload.
- Implement identifier mapping.
- Add mean, z-score, weighted, and rank-based scoring.
- Add GSVA/ssGSEA-style scoring.
- Add phenotype association.
- Add result pages and reports.
- Add signature records to database if useful.

Acceptance criteria:

- Mapping coverage is always shown.
- Per-sample score is reproducible.
- Missing genes are downloadable.
- Scores can be compared by phenotype.
- Signature analysis works for both RNA-seq-derived and microarray-derived log-expression assays.

## Phase 8: Cell-type deconvolution

Tasks:

- Implement method registry.
- Add EPIC and quanTIseq first.
- Add MCP-counter and xCell.
- Add method-specific validation.
- Build result-type-aware plots.
- Add cross-method comparison.
- Add CIBERSORTx as documentation and an external-result import adapter, not an automatic local dependency.

Acceptance criteria:

- Input scale is checked.
- Gene overlap is reported.
- Fraction outputs and enrichment-score outputs are never mislabeled.
- Selected methods produce separate and comparable result sections.
- External CIBERSORTx results can optionally be imported and displayed with provenance.

## Phase 9: Classifier development

Tasks:

- Implement binary elastic-net workflow.
- Implement grouped nested cross-validation.
- Produce out-of-fold predictions.
- Add metrics, confidence intervals, ROC, PR, calibration, and confusion matrix.
- Add feature stability.
- Add permuted-label control.
- Add model export and model card.
- Add random forest and boosted-tree comparisons.
- Add multiclass support.
- Add external test dataset support.
- Add `PREDICT_WITH_MODEL`.

Acceptance criteria:

- Automated tests prove no subject crosses folds.
- Automated leakage-trap test fails for an intentionally incorrect implementation and passes for the production implementation.
- Hyperparameter tuning occurs only inside training data.
- Out-of-fold predictions contain one prediction per eligible training sample per repeat.
- External test data is untouched until the locked model is ready.
- Model card and inference schema are generated.

## Phase 10: Cloud, security, and polish

Tasks:

- Add AWS Batch execution profile.
- Add S3 work and results locations.
- Add Terraform for a portfolio deployment.
- Add authentication or clearly documented single-user mode.
- Add quotas and upload limits.
- Add cancellation and cleanup.
- Add observability.
- Add demo video and screenshots.
- Add benchmark and cost notes.
- Add release workflow.

Acceptance criteria:

- Same analysis runs locally and on AWS Batch with only profile/config changes.
- No scientific source code changes are required for cloud execution.
- A tagged release builds immutable images.
- README contains a complete five-minute demo path.
- Public deployment contains no sensitive human data.

---

## 27. Implementation Priorities

Build in this order:

1. Matrix ingestion.
2. Canonical Expression Bundle.
3. Shared QC.
4. PCA vertical slice.
5. Differential expression.
6. Raw RNA-seq.
7. Microarray CEL.
8. Signature evaluation.
9. Deconvolution.
10. Classifier development.
11. External validation.
12. Cloud deployment.

Do not begin with raw FASTQ processing or classifier development. First prove the product architecture using small matrices and PCA.

---

## 28. First Codex Milestone

The first milestone should produce a working vertical slice, not the whole platform.

Codex should implement:

- Monorepo skeleton.
- Docker Compose.
- FastAPI, PostgreSQL, Redis, Celery, React.
- Project and dataset creation.
- Matrix and metadata upload.
- Count-matrix validation.
- Count-matrix preparation with Nextflow.
- Expression Bundle creation.
- Shared QC.
- PCA analysis.
- Run monitoring.
- Generic result-manifest rendering.
- Tests.
- A small human demo dataset.

Definition of done:

1. Run `make dev`.
2. Open the web UI.
3. Create a project.
4. Upload demo counts and metadata.
5. Prepare the dataset.
6. View QC.
7. Launch PCA.
8. Watch the Nextflow run complete.
9. Explore PCA interactively.
10. Download coordinates, loadings, report, parameters, and provenance.

Only after this milestone is stable should Codex implement differential expression.

---

## 29. Coding Standards

- Use strict typing in Python and TypeScript.
- Use Pydantic models at API boundaries.
- Use JSON schema for cross-language contracts.
- Keep scientific functions pure where feasible.
- Avoid global mutable state.
- Use dependency injection for storage and queue services.
- Use migrations for every database change.
- Use structured logs with project, dataset, analysis, and run IDs.
- Never expose arbitrary server paths to the user.
- Never interpolate user strings into shell commands.
- Launch Nextflow using argument arrays, not `shell=True`.
- Sanitize uploaded filenames and assign internal object keys.
- Write files atomically.
- Preserve immutable run inputs and parameters.
- Store random seeds.
- Record package, container, reference, and pipeline versions.
- Add docstrings and user-facing error messages.
- Keep API errors separate from scientific validation errors.
- Do not use placeholder statistical results.
- Do not silently catch analysis exceptions and mark runs successful.

---

## 30. Final Definition of Done

TranscriptForge is portfolio-ready when:

- All five analysis families work from the GUI.
- RNA-seq count matrices and normalized microarray matrices are fully supported.
- Raw FASTQ processing works.
- At least one raw Affymetrix CEL workflow works.
- Every run is reproducible from a frozen parameter file.
- Every run contains trace, report, timeline, DAG, logs, versions, and checksums.
- Scientific method routing is enforced.
- Classifier validation is leakage-resistant.
- Deconvolution output types are labeled correctly.
- Results are viewable and downloadable.
- Local Docker deployment is one command.
- At least one cloud execution profile works.
- CI exercises a complete small end-to-end analysis.
- The README tells a compelling technical and scientific story.
- The repository contains screenshots, architecture diagrams, demo data instructions, and a model card example.
- The platform clearly states that outputs are for research use and are not clinically validated.
