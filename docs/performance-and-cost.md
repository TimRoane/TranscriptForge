# Performance, benchmark, and cost notes

TranscriptForge separates deterministic software acceptance from biological validation. The full
regression inventory and exact run identities live in `docs/implementation-progress.md`; the README
summarizes the portfolio evidence without treating simulated data as clinical evidence.

## Representative workload evidence

- The 72-library synthetic RNA-seq study exercises ingestion, QC, four exploration methods, four
  differential-expression routes, enrichment, and signatures over 2,000 genes.
- The public GSE39795 acceptance independently RMA-normalizes eight CEL files and retains 257,430
  probe sets plus 23,702 mapped genes for paired limma and six signature methods.
- The GSE140494 classifier performs grouped repeated nested cross-validation and 100 complete
  leakage-safe permutations over 91 samples and 23,963 input genes. Permutations use deterministic
  index-derived seeds and completed on 32 workers with byte-identical serial/multicore artifacts.
- The one-shot GSE32646 evaluation scores 115 external samples at 500/500 locked-feature overlap and
  computes 2,000 deterministic stratified bootstrap intervals without refitting.

Wall time depends heavily on cache state, architecture, storage, and container availability. Record
elapsed time, peak memory, image digest, CPU allocation, cache-hit state, input checksum, and output
checksum when comparing environments; a single unqualified runtime number is not portable evidence.

## Cost model

Local Compose uses existing workstation resources. The optional AWS profile can incur charges for
Batch EC2/Spot runtime, EBS, S3 storage and requests, ECR image storage, KMS requests, CloudWatch logs,
NAT or VPC endpoints, and data transfer. The Terraform compute environment scales to zero and creates
an informational budget, but neither prevents every retry, egress path, or retained-object charge.

Before `terraform apply`, the owner must choose a Region, subnet/connectivity design, maximum vCPUs,
Spot policy, log retention, S3 lifecycle/retention policy, budget amount, and alert recipients. Use
the current AWS Pricing Calculator for that exact account/Region rather than copying a stale dollar
estimate into the repository. Run `make aws-batch-acceptance` only with explicit cost authorization;
it retains its S3 evidence by design.
