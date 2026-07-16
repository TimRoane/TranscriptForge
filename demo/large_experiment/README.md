# Multifactor paired RNA-seq demonstration

This deterministic synthetic study is designed to make exploratory visualizations meaningful while remaining small enough for local development.

## Design

- 72 libraries from 36 paired donors.
- Each donor contributes vehicle and stimulated samples at 24 hours.
- Two genotypes: wild type and variant.
- Three balanced processing batches.
- Sex is balanced within each genotype/batch stratum.
- 2,000 synthetic Ensembl-shaped human gene identifiers.

The nominal design is `~ batch + sex + genotype * treatment + subject_pair`. Controlled gene blocks encode treatment, genotype, genotype-by-treatment, batch, sex, and negative treatment effects. Remaining genes provide null and donor-level variation. The generator uses seed `20260716`.

The mock data are for software testing and visual demonstration only. They do not represent real people, biological measurements, or clinically meaningful effects.

## Files

- `data/counts.tsv`: feature-by-sample integer count matrix.
- `data/sample_metadata.tsv`: complete balanced experiment design.
- `data/ground_truth.tsv`: simulated effect assigned to every feature.
- `data/experiment_summary.json`: machine-readable design summary.
- `validation.json`: matrix-ingestion configuration.

Regenerate the files with `make generate-large-demo`. Seed them through the running API with `make seed-demo`.
