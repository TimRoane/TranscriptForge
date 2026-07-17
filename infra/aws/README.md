# TranscriptForge AWS Batch deployment

This directory contains an opt-in, cost-incurring portfolio deployment. Terraform creates no VPC or
NAT gateway: it deploys into owner-supplied private subnets so data locality, networking, and shared
account policy remain explicit decisions.

## What it provisions

- A managed EC2 or Spot AWS Batch compute environment with minimum and desired vCPUs set to zero.
- An encrypted, versioned, public-blocked S3 bucket with `inputs/`, `references/`, `work/`, and
  `results/` boundaries.
- An immutable ECR repository for the single scientific worker image.
- Customer-managed KMS encryption for S3, ECR, Batch instance disks, and CloudWatch Logs.
- Dedicated Batch service, compute-instance, and task roles plus a separate attachable Nextflow
  submitter policy.
- An informational AWS Budget, optionally with email alerts.

There is deliberately no EFS. A reference is stored as individual checksum-keyed S3 objects below
`references/<reference-id>/<definition-sha256>/materialization-<version>/`. Data objects are uploaded
first and `reference_materialization.json` is uploaded last. A Batch task accepts the prefix only
after downloading and verifying the complete manifest inventory.

## Owner prerequisites

Before applying, choose the AWS account/Region, data classification and residency policy, existing
VPC and private subnets, EC2 versus Spot, vCPU ceiling, budget, retention, and an identity/role for the
Nextflow head process. Private subnets need NAT or VPC endpoints that reach Batch, ECR API/DKR, S3,
CloudWatch Logs, STS, and KMS. Review [`docs/aws-batch-threat-model.md`](../../docs/aws-batch-threat-model.md)
before using real research data.

## Provision and configure

```bash
cd infra/aws/terraform
cp terraform.tfvars.example terraform.tfvars
# edit owner-specific values
terraform init
terraform plan -out transcriptforge.tfplan
terraform apply transcriptforge.tfplan
```

Attach the `nextflow_submitter_policy_arn` output to the role that runs Nextflow. No long-lived access
key belongs in `.env`, Terraform state, or Nextflow configuration.

Build the exact worker image and capture its digest:

```bash
repository="$(terraform output -raw scientific_ecr_repository)"
cd ../../..
image_digest="$(scripts/aws/build_scientific_image.sh "$repository")"
scripts/aws/render_batch_env.sh infra/aws/terraform "$image_digest" > .awsbatch.env
source .awsbatch.env
```

`.awsbatch.env` is local configuration and must not be committed. Validate configuration without
submitting work, then optionally perform read-only AWS control-plane checks:

```bash
python3 scripts/aws/validate_batch_profile.py
python3 scripts/aws/validate_batch_profile.py --live
```

## Scientific parity acceptance

The acceptance command incurs Batch, S3, ECR, KMS, and log charges. It runs the same paired tiny
FASTQ fixture locally and with `-profile awsbatch`, downloads the Batch publication, and compares the
declared deterministic scientific artifacts.

```bash
make aws-batch-acceptance
```

Evidence is written below `.transcriptforge-batch-acceptance/<timestamp>/scientific-parity.json`.
The S3 result prefix is retained intentionally for audit; remove it only under the approved retention
policy. A successful comparison closes the remaining live portion of TD-009.

## Destruction

The data bucket defaults to `force_destroy = false`, so Terraform cannot silently delete retained
research outputs. Empty or archive the bucket according to the owner-approved retention policy before
destroying the stack. KMS deletion has a 30-day default waiting period.
