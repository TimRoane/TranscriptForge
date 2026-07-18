# Five-minute portfolio walkthrough

This path is for a pre-seeded local workspace. The deterministic large study and public CEL study
are deliberately prepared outside the timed walkthrough because scientific workflows should not be
represented as instant UI demos.

## Before the walkthrough

```bash
cp .env.example .env
make dev
make generate-large-demo
make seed-demo
make seed-classifier-validation
```

The large-study seeder is idempotent. The classifier seeder requires the completed Phase 9 artifacts
described in `demo/classifier_external_validation/README.md` and never reruns the external model.

## 0:00–1:00 — Product and project record

Open <http://localhost:5173>. Point out the local single-user and research-only boundaries, then open
`TranscriptForge Visualization Study`. Show that source data, prepared versions, signatures, and
analysis history live in one project rather than being disconnected notebooks.

## 1:00–2:00 — Input contract and QC

Open the prepared 72-sample RNA-seq bundle. Review sample/feature counts, assay types, mapping
coverage, library/detection summaries, and saved analyses. Explain that matrix, FASTQ, and CEL paths
converge on the same checksum-versioned Expression Bundle.

## 2:00–3:00 — Reproducible exploration and inference

Open PCA, then one differential-expression analysis. Show the frozen seed/formula/contrast, live
plots, searchable table, gene detail, downloads, Quarto report, and Nextflow trace/timeline/DAG.
Mention that the R runner independently rebuilds and checks the design before fitting.

## 3:00–4:00 — Public microarray path

Open the public GSE39795 project. Show exact CEL/platform matching, RMA array QC, probe-to-gene
aggregation, and paired `~ donor + zone` limma result. Keep the honest zero-at-FDR-0.05 result visible;
the demo does not alter thresholds after inspection.

## 4:00–5:00 — Classifier governance and cloud portability

Open `Breast pCR Classifier Validation`. Compare internal nested-CV and untouched GSE32646 ROC-AUC,
then show the frozen pass/fail table and provenance downloads. The missed 0.65 gate is immutable and
has no tuning button. Close with the same Nextflow request boundary running locally or through the
opt-in Batch/S3 profile without scientific source changes.

The compact [walkthrough video](demo/transcriptforge-walkthrough.mp4) presents the same sequence from
the repository's real application captures. The README keeps the full-resolution images and detailed
scientific interpretation.
