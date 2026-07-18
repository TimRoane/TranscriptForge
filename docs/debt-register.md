# TranscriptForge debt register

Last reviewed: 2026-07-17

This is the owner-facing register for work that should not disappear inside implementation notes.
Items marked **Manual decision** need scientific, product, legal, infrastructure, or operational
judgment from the repository owner before they can be closed safely.

## High priority

### TD-001 — Durable object deletion and retention

- Type: Technical and operational
- Status: Open
- Manual decision: Choose retention periods, recovery expectations, and whether deletion is soft,
  delayed, or immediate.
- Current state: Project deletion now cascades through its complete relational ownership graph,
  including datasets, prepared bundles, analyses, runs, artifact indexes, models, and signatures.
  It does not yet enqueue deletion of every corresponding stored object, so immutable uploaded
  inputs and run artifacts can remain in storage.
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
- Status: Partially resolved
- Manual decision: Define cancellation semantics and which partial outputs should be retained for
  debugging.
- Current state: The API and UI cancel queued or locally executing validation, preparation, and
  analysis runs. Workers terminate the isolated Nextflow process group, acknowledge `CANCELLED`,
  restore dataset state, retain launcher logs, and allow interrupted reference materialization to
  remove its atomic temporary build. General run work directories remain retained, and cancellation
  across independently deployed API/worker control planes still needs an explicit remote transport.
- Exit criteria: Define retention for cancelled run work, add scheduled cleanup without deleting
  published immutable results, and implement/test AWS Batch cancellation from a separately deployed
  API control plane.

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
- Manual decision: Approve the final research-use disclaimer, privacy language, copyright-holder
  identity, PolyForm Noncommercial terms, commercial-license contact/process, and any deployment-
  specific terms with qualified counsel.
- Current state: The application consistently states that outputs are research-use only and not
  clinically validated. Repository-owned code and bundled synthetic collections are now marked
  PolyForm Noncommercial 1.0.0, but the wording and license transition have not received formal
  legal review. Copyright licensing does not protect the underlying product idea, and any copies
  already distributed under MIT retain the rights granted for those copies.
- Exit criteria: Review all user-visible warnings, reports, exports, and documentation; record the
  approved language and owner; confirm contributor authority and the license cutoff commit; publish
  a commercial-license contact path; and separately assess trademark, patent, and confidentiality
  strategy if protection beyond source-code copyright is required.

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
  choose the next supported Affymetrix platform and public validation study. Decide whether the
  portfolio should retain the current honest, low-powered public contrast or add a separate,
  prospectively selected higher-powered public study for positive differential-expression calls.
- Current state: Version 1 explicitly supports only Human Gene 1.0 ST through pinned Bioconductor
  design and annotation packages. An eight-CEL, four-donor public fixture proves real RMA execution,
  mapping, QC, bundle construction, and paired limma plumbing, but it is not an independent
  annotation benchmark. Other array families fail explicitly instead of guessing.
- Result interpretation: The paired superficial-versus-deep limma run tests 23,702 genes from four
  donors. It contains 2,084 genes at nominal p < 0.05, 665 at nominal p < 0.01, large effects in
  cartilage-relevant genes, and 53 genes at FDR < 0.20, but none at FDR < 0.05. The workflow should
  not lower FDR or select filters after seeing these results merely to manufacture significant calls.
- Exit criteria: Compare mappings and aggregation against an independent trusted reference; record
  annotation release/update semantics; then add a second checksum-pinned platform adapter with the
  same acceptance evidence. If a positive portfolio study is added, prespecify its study-selection
  and feature-filtering criteria before fitting the contrast. The replicated public limma benchmark
  criterion is complete.

### TD-014 — Signature scoring and cross-platform interpretation policy

- Type: Scientific content and product
- Status: Open
- Manual decision: Approve minimum mapping coverage, treatment of zero-variance genes, weight
  normalization, score comparability claims, the language shown when RNA-seq and microarray values
  produce scores on different scales, and when repeated-measures association should graduate from
  categorical subject fixed effects to a prespecified mixed-effects model.
- Current state: Mapping evidence is immutable and visible, including retained weights, missing
  identifiers, ambiguities, duplicates, and exact source checksums. Mean expression, mean z-score,
  weighted linear, rank-based, GSVA, and ssGSEA methods are deterministic with explicit formulas,
  frozen parameters, runtime/package provenance, and final-feature downloads. GSVA/ssGSEA ignore
  weights with an explicit warning and reject post-constant-filter sets outside configured bounds.
  Saved-score association now supports adjusted categorical/numeric linear models, multi-level
  omnibus tests, raw Pearson correlation, BH correction, and categorical subject/block fixed
  effects with rank and residual-degree-of-freedom guardrails. It does not fit random effects or
  claim causal/clinical interpretation. A deterministic cross-modality fixture now applies one
  checksum-identical weighted signature to independently built RNA-seq log2-CPM and microarray
  RMA-like bundles. Both recover the prespecified direction and rank discrimination while producing
  intentionally different raw score ranges; the contract and product explicitly prohibit raw-scale
  equivalence claims. Minimum coverage, default-method selection, association model policy, and
  thresholds on independent public cohorts still require owner approval.
- Exit criteria: Prespecify method-specific failure/warning thresholds; validate on synthetic and
  independent public cohorts; document within-cohort versus cross-cohort interpretation; approve
  report language and default method selection.

## Closed items

Move resolved items here with the closing date, pull request/commit, and evidence. Do not delete debt
history; it explains deliberate tradeoffs and scientific provenance decisions.
