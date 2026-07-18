# JSON Schemas

These JSON Schema 2020-12 contracts are the language-neutral boundary shared by the API, Nextflow, R, Python, and web client.

- `dataset_manifest.schema.json` describes immutable source inputs before preparation.
- `expression_bundle.schema.json` inventories prepared assays and metadata.
- `analysis_request.schema.json` freezes one downstream analysis request.
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

Every durable document includes a semantic `schema_version`. Consumers reject unknown major versions.
