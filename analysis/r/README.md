# R analysis runners

`differential_expression.R` is the independent scientific boundary for DESeq2, edgeR
quasi-likelihood, limma-voom, and limma runs. It
revalidates the immutable Expression Bundle and frozen model preview before fitting, then publishes
the common differential-expression result bundle.

Run its seeded acceptance harness through the pinned development runtime:

```bash
make test-r
```

The harness builds a temporary paired study with 100 annotated features and known positive,
negative, null, and low-count blocks. It asserts that formula/rank disagreements fail before model
fitting; every raw-count engine filters exactly the low-count block; all four engines preserve
numerator-minus-denominator direction; known effects are recovered; null calls remain bounded; and normalized
expression profiles retain every tested feature and sample. It uses base R assertions so no testing
package is added to the scientific runtime.
