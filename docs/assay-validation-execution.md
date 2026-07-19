# Assay-development execution evidence

## Local acceptance

On 2026-07-18, `make assay-validation-demo` executed all seven implemented templates through their real
Nextflow entry points with the repository `.venv` scientific runtime. A cold output-directory run
completed in 20.711 seconds on the development workstation. The command is cache-aware and an
immediately repeated command verifies existing manifests and archives without recomputation.

| Template | Domain | Result | Archive SHA-256 |
|---|---|---|---|
| Technical feasibility | Development Experiment | Evidence generated | `75a5f119f216275e435465a4554e2e0646d411724030d1f9c992eccc978c5a9e` |
| Paired condition | Development Experiment | Evidence generated | `c91d4348396b7f684399f59438bd4c28c1768df5eaf7b29899ccf0092e25356b` |
| Multifactor optimization | Development Experiment | Evidence generated | `714b39496f5b9afb39fce668867e3f89bcbb61e247d38ccadcd06b05dc466b6c` |
| Precision/reproducibility | Analytical Study | PASS | `bac1831020487041dbabe0bfb8a3db65c915379bf9c05647727de205b7691926` |
| Input/degradation limit | Analytical Study | PASS | `120dd17623b9f5c6087834411d9b68cc3204af910c60125ef4b8caba951379ee` |
| Paired bridging | Analytical Study | PASS | `aad9b5c3927f96feacf1f1714ae5b3ac9416413fb0dafcbd918cb91de5e80ab1` |
| Robustness/interference | Analytical Study | PASS | `014ead6b7baa8be5fa3a150d1e374ae09174ed3afb234dd12ff2d7250dcb7e98` |

The experiments are exploratory and therefore do not receive a PASS label. Every study manifest
records `model_retrained: false`; every template records `scientist_decision_required: true`. The
machine-readable local record is intentionally generated under ignored demo storage at
`.transcriptforge-demo/assay_development/portfolio/portfolio_execution_summary.json`.

## AWS Batch parity status

No live AWS job was submitted during this implementation pass. That would create external resources
and cost and requires the repository owner's account, Region, networking, budget, and explicit
authorization. This is an owner-gated acceptance item, not a claimed passing run.

The repository does provide the complete parity path:

1. `make terraform-check` validates the scale-to-zero Batch/S3/ECR/KMS infrastructure offline.
2. `make aws-batch-preflight` checks live queue, encryption, bucket, image-digest, and log controls
   without launching science.
3. `make aws-batch-acceptance` runs the cost-explicit local-versus-Batch harness and retains evidence
   in S3.
4. `scripts/aws/compare_scientific_artifacts.py` compares the declared deterministic artifact
   contract rather than assuming that a successful job state implies scientific parity.

The owner must attach the resulting job IDs, image digest, Region, elapsed time, cost observation,
and artifact comparison report before marking live cloud parity complete.

## Execution review

The [guided tutorial](guided_assay_development.md) is the assay-development walkthrough. The root
README's application captures and compact video demonstrate the shared navigation, immutable result
review, and artifact-download surfaces; this tutorial supplies the stage-specific validation path
without presenting scientific workflows as instant UI animations.
