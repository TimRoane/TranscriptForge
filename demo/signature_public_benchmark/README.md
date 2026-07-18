# Public signature-method benchmark

This fixture evaluates all six TranscriptForge signature-scoring methods against the public
GSE39795 human articular-cartilage cohort on GPL6244. It uses four matched donors with superficial
and deep cartilage samples and the same checksum-pinned RMA Expression Bundle produced by the
microarray acceptance workflow.

The two marker sets and their expected superficial-minus-deep directions were frozen before this
benchmark was run. The marker paper identifies SULF1 and VCAM1 as superficial-zone markers and
IBSP, SPP1, and COL10A1 as deep-zone markers. Because that publication includes this cohort, this is
a public technical benchmark, not independent biological or clinical validation.

## Frozen policy

- Mapping coverage must be at least 80%.
- Each comparison group must contain at least four samples.
- Every set must recover its expected direction, directional AUROC must be at least 0.80, and its
  block-adjusted association FDR must be at most 0.05.
- The recommended default must produce byte-identical JSON on a repeated run.
- A fixed, prespecified preference order selects among passing methods; observed effect magnitude
  is not used to choose a winner.
- Raw score cutoffs must not be transferred between cohorts, platforms, or preprocessing pipelines.

The accepted result has 100% mapping and directional AUROC 1.0 for both sets under all six methods.
The fixed policy recommends `mean_z_score` for transparent within-cohort direction, ranking, and
association without adding an R runtime dependency.

## Files

- `benchmark_policy.json`: prespecified dataset, signature, thresholds, and selection policy.
- `cartilage_zone_markers.gmt`: checksum-frozen Ensembl marker sets.
- `run_benchmark.py`: production Python and R scoring runner plus policy evaluation.
- `public_signature_benchmark.json`: schema-validated accepted result.
- `../../schemas/public_signature_benchmark.schema.json`: versioned result contract.

The raw CEL files are intentionally not stored in Git. Rebuild the public Expression Bundle with
`make test-microarray`, then pass the generated bundle archive to the pinned scientific worker:

```bash
make test-signature-public-benchmark \
  PUBLIC_SIGNATURE_BUNDLE=/path/to/gse39795-expression-bundle.tar.gz \
  PUBLIC_SIGNATURE_BENCHMARK_OUT=/tmp/transcriptforge-public-benchmark
```

Use a fresh output directory for each run. The runner refuses a bundle or signature whose SHA-256
differs from the frozen policy.

Sources: [NCBI GEO GSE39795](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE39795),
[GSE39797 SuperSeries](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE39797), and
[Grogan et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC3558601/).
