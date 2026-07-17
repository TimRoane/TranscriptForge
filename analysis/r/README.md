# R analysis runners

`differential_expression.R` is the independent scientific boundary for DESeq2, edgeR
quasi-likelihood, limma-voom, and limma runs. It
revalidates the immutable Expression Bundle and frozen model preview before fitting, then publishes
the common differential-expression result bundle. Optional enrichment verifies a versioned GMT
collection checksum before running seeded ranked-list enrichment and hypergeometric
over-representation analysis; its output freezes both collection and source-result provenance.

`signature_scoring.R` is the independent Bioconductor boundary for GSVA and ssGSEA. It verifies the
frozen mapping and bundle checksum, removes constant mapped genes visibly, rechecks the configured
gene-set size bounds, runs serially, and publishes the common Signature Scores contract with exact R
and package versions.

Run its seeded acceptance harness through the pinned development runtime:

```bash
make test-r
make test-signature-r
```

The harness builds a temporary paired study with 100 annotated features and known positive,
negative, null, and low-count blocks. It asserts that formula/rank disagreements fail before model
fitting; every raw-count engine filters exactly the low-count block; all four engines preserve
numerator-minus-denominator direction; known effects are recovered; null calls remain bounded; and normalized
expression profiles retain every tested feature and sample. It uses base R assertions so no testing
package is added to the scientific runtime. The edgeR case additionally checks known positive,
negative, and null gene sets across both enrichment modes and verifies every enrichment artifact.
The signature harness builds a temporary two-group log-expression study and verifies expected score
direction, constant-gene exclusion, complete artifacts, package provenance, and byte-identical
repeated JSON results for both GSVA and ssGSEA.
