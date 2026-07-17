# AWS Batch execution threat model

Last reviewed: 2026-07-16

## Scope and assets

The scope is the optional Nextflow `awsbatch` profile and Terraform under `infra/aws`. Protected
assets are uploaded reads and metadata, reference sources/indexes, scientific results, provenance,
container images, encryption keys, and the identities allowed to submit work. The API, identity
provider, and organization-wide AWS controls remain outside this deployment slice.

## Trust boundaries and controls

| Boundary | Principal | Allowed capability | Primary controls |
|---|---|---|---|
| Nextflow submission | Owner-selected worker role | Register/describe jobs, submit to Batch, pass one task role, use pipeline S3 prefixes | Attachable submitter policy; short-lived role credentials; no keys in config |
| Batch task | Dedicated ECS task role | Read/write only the data bucket's four pipeline prefixes and use one KMS key | Prefix-scoped S3 policy; digest-pinned image; no inbound security-group rules |
| Batch compute | Dedicated EC2 instance role | Join ECS and pull task images | AWS ECS instance policy; encrypted ephemeral gp3 volume; scale-to-zero environment |
| Object storage | S3 | Durable inputs, references, work, and results | Public access block, bucket-owner enforcement, versioning, TLS-only policy, SSE-KMS default |
| Reference reuse | S3 `references/` | Cross-run immutable index cache | Definition checksum/version in key; completion manifest last; complete SHA-256 revalidation |
| Logs and images | CloudWatch/ECR | Execution diagnostics and scientific runtime | KMS-encrypted log group; immutable ECR tags; scan on push; image digest required by preflight |

AWS Batch job-definition actions cannot be fully resource-scoped because Nextflow dynamically
registers job definitions. Data access and `iam:PassRole` remain narrowly scoped; the submitter policy
does not grant general IAM, EC2, KMS administration, or arbitrary S3 access.

## Threats addressed

- Public or plaintext object access is denied by S3 public-access-block, bucket ownership controls,
  HTTPS enforcement, and default SSE-KMS.
- Mutable container tags are rejected by preflight and the ECR repository enforces immutable tags;
  execution uses the resolved digest.
- Partial or conflicting reference uploads are not valid until the completion manifest exists, and
  all restored bytes are checked against the manifest before Salmon uses them.
- Stolen static credentials are avoided by relying on the AWS default credential chain and IAM roles.
- Runaway compute is limited by a fixed maximum-vCPU ceiling, zero idle capacity, bounded Nextflow
  submission rate, retry limits, log retention, and an AWS cost budget.
- Cross-project path guessing does not grant access outside the four deployment prefixes; application-
  level per-project authorization remains TD-002.

## Residual risks and owner decisions

- The owner must select Region/account/VPC, validate data residency, and decide whether NAT egress or
  private VPC endpoints meet policy. The supplied compute security group allows outbound traffic so
  containers can reach required AWS APIs and approved reference sources.
- AWS Budgets alert but do not enforce a hard spend stop. Account-level quotas and alerts are still
  required for stronger cost containment.
- ECR scan findings need an organizational severity/exception policy before production promotion.
- S3 object deletion, noncurrent-version retention, legal holds, and disaster recovery depend on the
  unresolved retention policy in TD-001.
- The full production reference must not be materialized until TD-004's source, storage, egress, and
  retirement decisions are approved.
- The AWS CLI v2 archive is version-pinned in the worker image but its detached signature is not yet
  verified during Docker build; this is tracked as TD-012.
- Live local/Batch parity needs an owner AWS account and incurs charges; offline config, Terraform,
  cache integrity, and comparison logic do not substitute for that acceptance run.
