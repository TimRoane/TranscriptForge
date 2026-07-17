# TranscriptForge debt register

Last reviewed: 2026-07-16

This is the owner-facing register for work that should not disappear inside implementation notes.
Items marked **Manual decision** need scientific, product, legal, infrastructure, or operational
judgment from the repository owner before they can be closed safely.

## High priority

### TD-001 — Durable object deletion and retention

- Type: Technical and operational
- Status: Open
- Manual decision: Choose retention periods, recovery expectations, and whether deletion is soft,
  delayed, or immediate.
- Current state: Deleting database records does not enqueue deletion of every corresponding object.
  Immutable uploaded inputs and run artifacts can therefore remain in storage.
- Exit criteria: Define retention policy; add an outbox/cleanup worker; make cleanup idempotent;
  audit storage versus database ownership; test partial-failure recovery.

### TD-002 — Authentication and multi-user authorization

- Type: Product security
- Status: Open
- Manual decision: Select the identity provider, deployment trust model, roles, and project-sharing
  rules.
- Current state: Development records use the fixed owner `local-user`. This is appropriate only for
  local development and demonstration.
- Exit criteria: Authenticate every request, enforce project/object ownership at service boundaries,
  add audit events, and complete a deployment-focused security review.

### TD-003 — Curated enrichment catalog

- Type: Scientific content
- Status: Open
- Manual decision: Select catalogs and releases, approve their licenses/redistribution terms, and
  decide supported identifier namespaces.
- Current state: The bundled enrichment collection contains synthetic controls for the deterministic
  demonstration experiment. It is deliberately not presented as a biological pathway database.
- Exit criteria: Add approved, versioned collections with source/license records and checksums;
  benchmark identifier coverage; document update cadence and retirement policy.

### TD-004 — Production human reference policy

- Type: Scientific content and operations
- Status: Open
- Manual decision: Approve the production annotation cadence, whether older reference bundles stay
  runnable, and the storage/egress budget for reference assets and Salmon indexes.
- Current state: The local workflow verifies source MD5 and derived SHA-256 values, rejects Salmon
  version drift, and caches indexes by the exact reference-definition digest. The tiny reference is
  acceptance-tested, but the multi-gigabyte production GENCODE reference/index has not yet been
  materialized in this development environment. Pinning does not establish an organizational update
  policy.
- Exit criteria: Approve source and license/terms review; materialize and checksum every source and
  derived asset; publish update/deprecation policy; verify disaster recovery for cached indexes.

## Medium priority

### TD-005 — Run cancellation and abandoned-work cleanup

- Type: Technical and operational
- Status: Open
- Manual decision: Define cancellation semantics and which partial outputs should be retained for
  debugging.
- Current state: Run states include cancelling/cancelled values, but end-to-end Nextflow cancellation,
  worker acknowledgement, and work-directory cleanup are not implemented.
- Exit criteria: Add cancellation API/UI, terminate the correct workflow session, preserve actionable
  logs, and clean work data without deleting published immutable results.

### TD-006 — Frontend bundle size

- Type: Technical
- Status: Open
- Manual decision: None unless a performance budget is desired.
- Current state: The production build succeeds but reports a JavaScript chunk above 500 kB.
- Exit criteria: Establish a bundle/performance budget and lazy-load analysis routes or heavy
  visualization dependencies until the warning is resolved.

### TD-007 — Independent biological validation corpus

- Type: Scientific content
- Status: Open
- Manual decision: Select public datasets, acceptable licenses, expected biological signals, and
  pass/fail tolerances.
- Current state: Deterministic synthetic fixtures test direction, null behavior, reproducibility,
  contracts, and workflow plumbing. They do not establish external biological validity.
- Exit criteria: Add documented public benchmark datasets with frozen accessions/checksums and
  prespecified acceptance metrics for every scientific module.

### TD-008 — Research-use language and legal review

- Type: Product content and legal
- Status: Open
- Manual decision: Approve the final research-use disclaimer, privacy language, and any deployment-
  specific terms.
- Current state: The application consistently states that outputs are research-use only and not
  clinically validated, but the wording has not received formal legal review.
- Exit criteria: Review all user-visible warnings, reports, exports, and documentation; record the
  approved language and owner.

### TD-015 — Docker-profile bundle-builder runtime

- Type: Technical and workflow operations
- Status: Open
- Manual decision: None.
- Current state: The Docker profile assigns Expression Bundle construction to the generic
  `python:3.12-slim` image. Nextflow's task-metrics wrapper requires `ps`, which that image does not
  provide, so the scientific Affymetrix RMA process can succeed while the following Python bundle
  process fails before its command starts. The tested Python package itself builds and validates the
  bundle successfully, and the local worker profile is unaffected.
- Exit criteria: Replace the generic image with a digest-pinned TranscriptForge bundle-builder image
  containing the required runtime utilities and Python dependencies; run matrix, raw RNA-seq, and
  microarray preparation end to end under the Docker profile; assert artifact paths match the worker
  indexer's expectations.

## Later-phase infrastructure decisions

### TD-009 — AWS Batch production profile

- Type: Infrastructure
- Status: Implemented offline; owner-account acceptance pending as of 2026-07-16
- Manual decision: Choose AWS account/VPC, Batch compute environments, IAM boundaries, encryption,
  logging, budgets, data locality, and secrets management.
- Current state: The repository contains a validated AWS Batch Nextflow profile, Terraform for a
  scale-to-zero EC2/Spot environment, prefix-scoped S3/KMS IAM, encrypted S3/ECR/EBS/Logs, immutable
  digest-pinned images, an S3 reference cache with checksum revalidation, a threat model, read-only
  preflight, and a local/Batch scientific comparison harness. EFS was intentionally excluded. No AWS
  resources were created and no billable parity run was made without an owner account and approval.
- Exit criteria: Threat-model the profile, provision it as code, run the same tiny FASTQ acceptance
  data locally and on Batch, and compare published scientific checksums where tools permit. The first
  two criteria are complete; provisioning and live checksum evidence remain.

### TD-010 — Reference and dependency update automation

- Type: Technical and scientific operations
- Status: Open
- Manual decision: Approve how scientific version upgrades are reviewed and when they are allowed to
  change expected results.
- Current state: Containers, schemas, collections, and reference definitions are pinned manually.
- Exit criteria: Add release monitoring, checksum verification, controlled rebuilds, scientific
  regression review, and explicit version-retirement records.

### TD-011 — Raw RNA-seq scope beyond the local MVP

- Type: Technical and scientific
- Status: Partially resolved on 2026-07-16
- Manual decision: Prioritize multiple-lane libraries, durable transcript-level abundance, optional
  STAR/featureCounts, and the expanded RNA-seq QC metric set.
- Current state: Explicit lane rows now merge deterministically at the biological-sample boundary;
  transcript counts/TPM/effective lengths and every `quant.sf` are durable; gene-type/chromosome
  annotations drive mitochondrial/ribosomal percentages; and mapping, detection, correlation, and
  PCA review metrics flag without excluding samples. Remaining debt is threshold calibration on a
  larger public validation corpus and the optional alignment-based STAR/featureCounts path.
- Exit criteria: Extend the ingestion contract without filename guessing; add lane-aware acceptance
  data; retain transcript-level results; add identifier-aware QC and conservative outlier summaries;
  document storage impact and scientific defaults. All criteria except public-corpus calibration
  and the optional alignment-path decision are now met.

### TD-012 — AWS CLI installer signature verification

- Type: Supply-chain security
- Status: Open
- Manual decision: Approve the trusted AWS CLI signing-key update process or replace CLI-based S3
  staging with an approved Wave/Fusion deployment.
- Current state: The scientific worker pins the AWS CLI v2 archive version and downloads it from the
  official AWS distribution endpoint, but the Docker build does not yet verify its detached PGP
  signature. Scientific executables with published stable SHA-256 values remain checksum-pinned.
- Exit criteria: Store an independently verified AWS public-key fingerprint, verify the detached
  signature in the image build, document key rotation, and fail builds on signature mismatch.

### TD-013 — Affymetrix annotation policy and platform expansion

- Type: Scientific content and technical
- Status: Open
- Manual decision: Approve the Human Gene 1.0 ST probe/transcript-cluster/gene mapping policy and
  choose the next supported Affymetrix platform and public validation study.
- Current state: Version 1 explicitly supports only Human Gene 1.0 ST through pinned Bioconductor
  design and annotation packages. An eight-CEL, four-donor public fixture proves real RMA execution,
  mapping, QC, bundle construction, and paired limma plumbing, but it is not an independent
  annotation benchmark. Other array families fail explicitly instead of guessing.
- Exit criteria: Compare mappings and aggregation against an independent trusted reference; record
  annotation release/update semantics; then add a second checksum-pinned platform adapter with the
  same acceptance evidence. The replicated public limma benchmark criterion is complete.

### TD-014 — Signature scoring and cross-platform interpretation policy

- Type: Scientific content and product
- Status: Open
- Manual decision: Approve minimum mapping coverage, treatment of zero-variance genes, weight
  normalization, score comparability claims, and the language shown when RNA-seq and microarray
  values produce scores on different scales.
- Current state: Mapping evidence is immutable and visible, including retained weights, missing
  identifiers, ambiguities, duplicates, and exact source checksums. Mean expression, mean z-score,
  weighted linear, rank-based, GSVA, and ssGSEA methods are deterministic with explicit formulas,
  frozen parameters, runtime/package provenance, and final-feature downloads. GSVA/ssGSEA ignore
  weights with an explicit warning and reject post-constant-filter sets outside configured bounds.
  Minimum coverage, default-method selection, and cross-cohort/platform interpretation policy still
  require owner approval; no clinical or raw score-scale equivalence claim is made.
- Exit criteria: Prespecify method-specific failure/warning thresholds; validate on synthetic and
  independent public cohorts; document within-cohort versus cross-cohort interpretation; approve
  report language and default method selection.

## Closed items

Move resolved items here with the closing date, pull request/commit, and evidence. Do not delete debt
history; it explains deliberate tradeoffs and scientific provenance decisions.
