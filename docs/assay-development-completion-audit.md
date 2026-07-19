# Assay-development amendment completion audit

This audit maps the revised amendment to durable implementation evidence. It was completed against
the authoritative amendment on 2026-07-18 after a route-level review found and closed one advertised
but previously unreachable `TECHNICAL_FEASIBILITY` workflow.

## Phase evidence

| Phase | Status | Primary evidence |
|---|---|---|
| G0 — contracts and scaffolding | Complete | Versioned schemas/examples under `contracts/`, static question catalog, feature flags, and contract/catalog tests. The canonical amendment is linked into the docs set. |
| G1 — dashboard and readiness | Complete | Assay project/question/recommendation/decision/audit persistence and APIs; deterministic readiness rules; stage rail, evidence cards, question wizard, and accept/reject/modify UI/API tests. |
| G2 — pre-lock vertical slice | Complete | Input/degradation and technical-feasibility designs, immutable revisions, Nextflow execution, wet-lab export, schema-valid Development Evidence Bundles, decision summaries, recommendations, follow-up drafts, and cancellation/clone boundaries. |
| G3 — existing analyses | Complete | Guided PCA, differential expression, deconvolution, signature, and classifier launchers reuse existing builders and persist checksummed GuidanceResult references. |
| G4 — model locking | Complete | Candidate/reviewed/locked/retired lifecycle, lock readiness, immutable ModelManifest/package, clone/retire/integrity APIs and GUI, hardened deterministic prediction, and tamper tests. |
| G5 — precision vertical slice | Complete | Locked-model study lifecycle, design validation, precision/variance/ICC/agreement/threshold calculations, criteria engine, Validation Bundle, dashboard routing, and no-retraining tests. |
| G6 — added templates | Complete | Paired condition, input/degradation limit, paired bridging, robustness/interference, and constrained multifactor optimization each have schema, design, scientific, API, GUI, and direct Nextflow coverage. |
| G7 — portfolio polish | Locally complete; cloud execution owner-deferred | One-command seven-template demo, architecture diagram, guided tutorial, screenshots/walkthrough, runtime/checksum evidence, cost notes, and human-judgment boundaries. AWS infrastructure/preflight/parity tooling is implemented; a live charged run was explicitly deferred by the owner. |

## Expanded definition-of-done audit

- The guided workspace exposes stage, current evidence, missing information, blockers, warnings,
  recommendation rules, alternatives, and the next controlled action.
- Every cataloged Development Experiment and Analytical Study route is checked against an
  implemented lifecycle handler by regression test; plain-language analysis routes reuse existing
  scientific workflows.
- Design validators block missing pairs, missing metadata, confounding, sparse/rank-deficient
  designs, and uncomputable criteria while retaining explicit retrospective warnings.
- Experiment and study inputs are frozen and checksummed; locked revisions are immutable and edits
  require cloning. Model assets and prediction contracts fail integrity checks after tampering.
- Every experiment publishes a decision summary and scientist-controlled next action. Material
  recommendations require accept, reject, modify, or defer rationale and never auto-launch work.
- Precision plus three additional post-lock study templates run without retraining and return
  `PASS`, `FAIL`, `INDETERMINATE`, or `NOT_APPLICABLE` at the criterion boundary.
- Development Evidence and Validation Bundles include machine-readable manifests, reports,
  endpoints, provenance, versions, workflow metadata, checksums, limitations, and explicit
  research-use boundaries.
- The same experiment/study specs execute through local or AWS profiles. Local execution is proven;
  live AWS parity remains an honest owner-gated acceptance item because it requires account access,
  infrastructure choices, and cost authorization.

## Acceptance commands

```bash
make assay-validation-demo
make test
make lint
make terraform-check
make aws-batch-preflight   # requires owner AWS configuration; does not launch science
make aws-batch-acceptance  # requires explicit owner cost authorization
```

The exact local seven-template runtime and SHA-256 evidence are in
[`assay-validation-execution.md`](assay-validation-execution.md). Full regression counts and the
authoritative virtual-environment/Node 22 toolchain are recorded in
[`implementation-progress.md`](implementation-progress.md).
