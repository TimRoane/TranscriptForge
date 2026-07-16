# Python analysis library

`transcriptforge_analysis` contains workflow-owned scientific validation and analysis functions. CLI modules are deliberately thin wrappers around typed, directly tested library functions.

The first implemented command validates count/expression matrices and sample metadata:

```bash
python -m transcriptforge_analysis.cli \
  --config demo/configs/count_matrix_validation.json \
  --output validation_report.json \
  --manifest-output dataset_manifest.json
```

A validated matrix can then be converted into a canonical Expression Bundle:

```bash
python -m transcriptforge_analysis.bundle_cli \
  --config demo/configs/count_matrix_validation.json \
  --matrix demo/data/counts.tsv \
  --metadata demo/metadata/sample_metadata.tsv \
  --output-dir prepared
```

The builder emits an immutable bundle archive, raw-count and log-expression assays, mapping reports, sample QC, previews, provenance, and a schema-valid bundle manifest.
