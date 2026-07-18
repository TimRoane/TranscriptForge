# Prospective external classifier validation

`gse32646_protocol.json` freezes the first real TranscriptForge classifier validation before any
external expression values, predictions, feature associations, or performance metrics are viewed.
It is validated by `classifier_external_validation_protocol.schema.json`.

The planned development cohort is the 91-sample, prospective multicenter GSE140494 trial. The
untouched external cohort is GSE32646: 115 pretreatment breast-tumor biopsies from Osaka University
with 27 public pCR and 88 nCR labels. Both use Affymetrix GPL570, allowing one frozen annotation and
feature mapping while still testing transport across institution, country, biopsy workflow, and
chemotherapy regimen.

This directory does not contain an external-validation result. The permitted sequence is:

1. Add a checksum-pinned GPL570 preparation adapter and independently RMA-normalize each cohort.
2. Develop and internally validate the model using GSE140494 only.
3. Freeze the locked model, model card, inference schema, feature mapping, and decision threshold.
4. Run `PREDICT_WITH_MODEL` exactly once against the compatible GSE32646 Expression Bundle.
5. Only after prediction checksums exist, join the frozen pCR/nCR truth and calculate the
   prespecified metrics.

The primary success gate is ROC-AUC at least 0.65 with a two-sided 95% bootstrap lower bound above
0.50. Passing that gate would support only a research transportability statement, not a clinical or
diagnostic claim.

Primary records:

- [GSE140494](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE140494)
- [GSE32646](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE32646)
