# JSON Schemas

These JSON Schema 2020-12 contracts are the language-neutral boundary shared by the API, Nextflow, R, Python, and web client.

- `dataset_manifest.schema.json` describes immutable source inputs before preparation.
- `expression_bundle.schema.json` inventories prepared assays and metadata.
- `analysis_request.schema.json` freezes one downstream analysis request, including classifier
  outcome direction, grouped repeated nested CV, and training-fold-only leakage controls.
- `result_manifest.schema.json` drives generic result rendering.
- `sample_metadata.schema.json` describes the required tabular sample-metadata contract.
- `validation_report.schema.json` describes actionable matrix/metadata findings and previews.
- `reference_bundle.schema.json` pins external human reference assets and index parameters.
- `raw_rnaseq_ingestion.schema.json` freezes a validated FASTQ sample sheet, read checksums, layout,
  strandedness, and reference definition.
- `microarray_platform.schema.json` defines a checksum-pinned Affymetrix platform adapter and its
  Bioconductor normalization and annotation dependencies.
- `microarray_ingestion.schema.json` freezes exact CEL-to-sample assignments, CEL checksums,
  platform identity, RMA settings, and gene-level aggregation policy.
- `signature_definition.schema.json` freezes uploaded gene-list/GMT contents, identifier namespace,
  optional weights, duplicate accounting, and source-object checksum.
- `signature_mapping.schema.json` freezes definition and Expression Bundle checksums, mapped
  features and weights, coverage, duplicates, missing identifiers, and ambiguous identifiers.
- `signature_scores.schema.json` freezes method semantics, mapping and bundle provenance, final
  scored-feature counts, per-sample scores, aligned metadata, and scientific warnings.
- `deconvolution_method_registry.schema.json` separates fraction-producing, enrichment-score, and
  external-import methods while declaring accepted assay scales and identifier requirements.
- `deconvolution_results.schema.json` requires gene-overlap evidence, reference checksums,
  result-type-specific units, per-sample estimates, and composition summaries only for fractions.
  CIBERSORTx results additionally require an external source checksum, explicit relative-mode
  declaration, signature checksum, external run/runtime record, and batch/permutation provenance.
- `classifier_results.schema.json` requires complete repeated out-of-fold coverage, fold-level
  tuning and leakage evidence, uncertainty, diagnostics, negative controls, comparison models,
  feature stability, locked-model references, and immutable provenance.
- `classifier_model.schema.json` defines the locked binary feature/scaling/estimator/calibration and
  decision-threshold recipe; `classifier_prediction_results.schema.json` requires complete feature
  compatibility plus checksummed model/bundle provenance for every external prediction run.
- `multiclass_classifier_results.schema.json`, `multiclass_classifier_model.schema.json`, and
  `multiclass_classifier_prediction_results.schema.json` preserve the same leakage and inference
  boundaries for multinomial elastic net with classwise probabilities and macro metrics.
- `classifier_external_validation_protocol.schema.json` freezes cohort identity, endpoint mapping,
  preprocessing, model-lock prerequisites, one-use evaluation policy, success criteria, and the
  information inspected before a real external cohort is evaluated.
- `classifier_external_validation_results.schema.json` records the one-shot locked-model metrics,
  stratified bootstrap intervals, prespecified pass/fail decision, and checksums for the frozen
  protocol, prediction artifact, separately sealed truth, model, and Expression Bundle.

Every durable document includes a semantic `schema_version`. Consumers reject unknown major versions.
