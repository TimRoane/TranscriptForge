# Public Affymetrix microarray demo

This fixture uses eight public Human Gene 1.0 ST CEL files from NCBI GEO study GSE39795
(platform `GPL6244`). Four donors each contribute matched deep and superficial cartilage-zone
samples. The download script pins every HTTPS URL and SHA-256 checksum. The files total
approximately 30 MiB and are downloaded on demand; they are not committed to the repository.

Run the RMA execution acceptance check after building the scientific image:

```bash
docker build -t transcriptforge/microarray:bioc-3.23 containers/microarray
demo/microarray/run_acceptance.sh
```

The check reads both CEL files with `oligo`, verifies the frozen platform design package, performs
RMA, emits probe-set and Ensembl gene-level expression, records probe mapping and highest-MAD
aggregation, and creates array intensity, PCA, and correlation QC outputs. It then validates and
archives the same outputs as a canonical Expression Bundle with `log_expression` and
`probe_expression` assays. Each acceptance run writes its bundle to a unique ignored directory under
`.transcriptforge-demo/microarray/` so immutable results are never overwritten. Finally, the
existing differential-expression runner fits the full-rank paired design `~ donor + zone` with
limma and verifies all 23,702 gene results, eight-sample normalized profiles, explicit superficial-
minus-deep contrast weights, plots, tables, report source, and session provenance.

This is an observational public study with four paired donors, not independent product validation.
The acceptance check proves statistical and provenance plumbing; do not treat its exploratory
contrast as a clinical conclusion. The source records remain governed by NCBI GEO's terms and the
original submitter's data-use statements.
