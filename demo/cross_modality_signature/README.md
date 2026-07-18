# Cross-modality signature acceptance

This deterministic acceptance fixture evaluates one checksum-frozen weighted Ensembl signature in
two independent, platform-specific Expression Bundles:

- an RNA-seq bundle containing raw counts and log2 CPM derived from those counts;
- a microarray bundle containing RMA-like log2 gene and probe expression with explicit platform
  provenance.

The fixture intentionally gives the two platforms different raw score ranges. Acceptance compares
mapping coverage, within-cohort phenotype direction, adjusted association significance,
rank discrimination (AUROC), and standardized effects. It explicitly fails any contract that claims
the raw RNA-seq and microarray score scales are interchangeable.

Run it with:

```bash
make test-signature-cross-modality
```

This is workflow/scientific plumbing acceptance using synthetic data. It is not an independent
biological validation cohort and does not establish a clinically useful threshold.
