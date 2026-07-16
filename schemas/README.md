# JSON Schemas

These JSON Schema 2020-12 contracts are the language-neutral boundary shared by the API, Nextflow, R, Python, and web client.

- `dataset_manifest.schema.json` describes immutable source inputs before preparation.
- `expression_bundle.schema.json` inventories prepared assays and metadata.
- `analysis_request.schema.json` freezes one downstream analysis request.
- `result_manifest.schema.json` drives generic result rendering.
- `sample_metadata.schema.json` describes the required tabular sample-metadata contract.
- `validation_report.schema.json` describes actionable matrix/metadata findings and previews.

Every durable document includes a semantic `schema_version`. Consumers reject unknown major versions.
