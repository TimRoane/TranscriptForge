# Frozen external classifier validation

`gse32646_protocol.json` freezes the first real TranscriptForge classifier validation before any
external expression values, predictions, feature associations, or performance metrics are viewed.
It is validated by `classifier_external_validation_protocol.schema.json`.

The development cohort is the 91-sample, prospective multicenter GSE140494 trial. The one-use
external cohort is GSE32646: 115 pretreatment breast-tumor biopsies from Osaka University
with 27 public pCR and 88 nCR labels. Both use Affymetrix GPL570, allowing one frozen annotation and
feature mapping while still testing transport across institution, country, biopsy workflow, and
chemotherapy regimen.

The protocol was executed once in its permitted order:

1. Add a checksum-pinned GPL570 preparation adapter and independently RMA-normalize each cohort.
2. Develop and internally validate the model using GSE140494 only.
3. Freeze the locked model, model card, inference schema, feature mapping, and decision threshold.
4. Run `PREDICT_WITH_MODEL` exactly once against the compatible GSE32646 Expression Bundle.
5. Only after prediction checksums exist, join the frozen pCR/nCR truth and calculate the
   prespecified metrics.

`gse32646_external_validation_result.json` is the schema-valid durable record of that execution.
The locked model achieved external ROC-AUC 0.619 (95% stratified bootstrap interval 0.503–0.726),
PR-AUC 0.312, balanced accuracy 0.588, sensitivity 0.778, and specificity 0.398. The lower ROC-AUC
bound passed the frozen above-0.50 requirement, but the point estimate did not reach 0.65, so the
overall status is `SUCCESS_CRITERIA_NOT_MET`. The cohort, features, calibration, threshold, endpoint,
and success criteria were not modified, and prediction was not rerun. The locked threshold predicted
74/115 samples positive while 27 were observed positive; the resulting low specificity and
calibration intercept -0.334 make threshold/probability transport a documented failure mode.

With the local stack running, import the completed study into the application with:

```bash
make seed-classifier-validation
```

The idempotent seeder creates (or reuses) the `Breast pCR Classifier Validation` project and imports
the frozen protocol, locked model, development results, external predictions, and final evaluation.
The API verifies their schemas, checksums, analysis identifiers, cohort counts, and reported
development metrics before the GUI exposes the read-only results dashboard and artifact downloads.

Raw inputs are reproducibly materialized with `download_cohorts.sh`; `prepare_bundles.sh` then uses
the repository `.venv` plus the pinned Bioconductor container to build both independent Expression
Bundles. The script refuses to overwrite an existing frozen cohort directory. Both GEO tar archives
and the metadata-only MINiML responses are SHA-256 pinned; `prepare_geo_cohort.py` rejects checksum,
sample, class-count, archive-membership, or endpoint-vocabulary drift. Development metadata maps
GSE140494 `pCR` to the positive class and `pPR`/`pNC` to `nCR`. External prediction metadata
deliberately omits the response, while the exact GSE32646 truth table is written separately under
`sealed_truth`.

The primary success gate was ROC-AUC at least 0.65 with a two-sided 95% bootstrap lower bound above
0.50. Because only the lower-bound criterion passed, the result supports weak above-chance transport
in this cohort but not the frozen research transportability success claim. It is not clinical or
diagnostic validation.

Primary records:

- [GSE140494](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE140494)
- [GSE32646](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE32646)
