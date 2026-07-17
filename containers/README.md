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

## GSVA and ssGSEA

`signature-scoring/Dockerfile` uses the official Bioconductor `RELEASE_3_23` image and installs
GSVA plus jsonlite. Build the production workflow image with:

```bash
docker build -t transcriptforge/signature-scoring:bioc-3.23 \
  containers/signature-scoring
```

The Compose development worker selects the Bioconductor 3.22 repositories and currently records
R 4.5.0, GSVA 2.4.9, BiocParallel 1.40.0, and jsonlite 1.9.1 for local/test-profile execution.
Production uses the dedicated Bioconductor 3.23 image. Every result records the actual R, GSVA,
BiocParallel, and jsonlite versions, so runtime provenance remains explicit across profiles.

## Affymetrix microarray

`microarray/Dockerfile` uses the official Bioconductor `RELEASE_3_23` image and installs
`oligo`, the `pd.hugene.1.0.st.v1` platform design package, and the
`hugene10sttranscriptcluster.db` annotation package used by the first explicit platform adapter.
Build it with:

```bash
docker build -t transcriptforge/microarray:bioc-3.23 containers/microarray
```

The adapter definition, expected CEL chip-type aliases, RMA target, annotation package, and
probe aggregation policy are versioned separately under `microarray/platforms/`.

Run the deterministic runner-level acceptance fixtures in the pinned development image with
`make test-r` and `make test-signature-r`. The DE harness rejects frozen-design disagreements and
checks filtering, contrast direction, known-effect recovery, null calls, feature annotations, and expression-profile outputs
for DESeq2, edgeR quasi-likelihood, limma-voom, and limma. The signature harness checks GSVA/ssGSEA
direction, constant-feature handling, software provenance, and deterministic reruns. CI builds the
same worker target and runs both harnesses independently of the Python and frontend suites.
