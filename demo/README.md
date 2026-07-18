# Demonstration data

Two deterministic synthetic studies are included:

- The compact four-sample matrix supports fast ingestion and PCA contract tests.
- [`large_experiment`](large_experiment/README.md) is a balanced 72-library paired genotype-treatment experiment with three batches, 2,000 genes, known simulated effects, and enough structure for PCA, clustering, UMAP, and t-SNE demonstrations.
- [`cross_modality_signature`](cross_modality_signature/README.md) freezes one weighted Ensembl
  signature and verifies mapping, direction, association, and rank discrimination independently in
  RNA-seq and microarray bundles while rejecting raw score-scale equivalence.

Larger public datasets will use accession-based download scripts after redistribution terms are reviewed.
