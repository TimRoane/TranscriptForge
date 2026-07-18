# Demonstration data

Two deterministic synthetic studies are included:

- The compact four-sample matrix supports fast ingestion and PCA contract tests.
- [`large_experiment`](large_experiment/README.md) is a balanced 72-library paired genotype-treatment experiment with three batches, 2,000 genes, known simulated effects, and enough structure for PCA, clustering, UMAP, and t-SNE demonstrations.
- [`cross_modality_signature`](cross_modality_signature/README.md) freezes one weighted Ensembl
  signature and verifies mapping, direction, association, and rank discrimination independently in
  RNA-seq and microarray bundles while rejecting raw score-scale equivalence.
- [`signature_public_benchmark`](signature_public_benchmark/README.md) evaluates all six scoring
  methods against checksum-frozen GSE39795 cartilage-zone signatures and records the prespecified
  80% mapping threshold and mean-z-score default policy.

Public raw files are downloaded by accession and checksum rather than redistributed in this repository.
