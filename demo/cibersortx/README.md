# CIBERSORTx external-result import

TranscriptForge does not execute CIBERSORTx, handle credentials, bundle proprietary resources, or
accept upstream terms. The Expression Bundle page exposes an import form for a completed
CIBERSORTx **relative-mode** export.

The result table must be UTF-8 TSV or CSV with `Mixture` as its first column, one fraction column per
cell population, and optional standard diagnostic columns (`P-value`, `Correlation`, and `RMSE`).
Its sample identifiers must exactly match the selected Expression Bundle. Every fraction must be
finite and between zero and one, and each sample must sum to one within 0.02.

The form also requires:

- the exact linear, nonnegative TPM assay sent to CIBERSORTx;
- an explicit declaration that values are relative fractions;
- signature name, version, SHA-256, and gene count;
- mixture and overlapping-signature gene counts;
- CIBERSORTx version, external run identifier, and timezone-aware completion time;
- batch-correction mode and permutation count.

On acceptance, TranscriptForge preserves the original export byte-for-byte, computes its SHA-256,
creates a canonical fraction table, validates the durable deconvolution-result contract, and indexes
all source/result/provenance artifacts under an immutable successful external-import run.
