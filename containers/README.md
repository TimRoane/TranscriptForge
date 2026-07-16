# Scientific containers

Purpose-built scientific runtimes live beside the workflow source that consumes them. Every
analysis records its actual package and language versions in immutable run artifacts.

## Differential expression

`differential-expression/Dockerfile` uses the official Bioconductor `RELEASE_3_23` image and
installs DESeq2, limma, edgeR, and jsonlite. Build the production workflow image with:

```bash
docker build -t transcriptforge/differential-expression:bioc-3.23 \
  containers/differential-expression
```

The Compose development worker uses version-pinned Debian R 4.5.0, DESeq2 1.46.0, edgeR 4.4.2,
and limma 3.62.2 packages because the Nextflow test profile runs processes directly inside that worker.
Production runs use the dedicated container.

Run the deterministic runner-level acceptance fixtures in the pinned development image with
`make test-r`. The harness rejects frozen-design disagreements and checks filtering, contrast
direction, known-effect recovery, null calls, feature annotations, and expression-profile outputs
for DESeq2, edgeR quasi-likelihood, limma-voom, and limma. CI builds the same worker target and runs
this harness independently of the Python and frontend suites.
