#!/usr/bin/env bash
set -euo pipefail

terraform_dir="${1:-infra/aws/terraform}"
scientific_image="${2:-}"
if [[ -z "${scientific_image}" || "${scientific_image}" != *@sha256:* ]]; then
  echo "Usage: $0 [terraform-dir] <ecr-image@sha256:digest>" >&2
  exit 2
fi

tf_output() {
  terraform -chdir="${terraform_dir}" output -raw "$1"
}

printf 'export TRANSCRIPTFORGE_AWS_REGION=%q\n' "$(tf_output aws_region)"
printf 'export TRANSCRIPTFORGE_AWS_BATCH_QUEUE=%q\n' "$(tf_output batch_job_queue)"
printf 'export TRANSCRIPTFORGE_AWS_BATCH_JOB_ROLE_ARN=%q\n' "$(tf_output batch_job_role_arn)"
printf 'export TRANSCRIPTFORGE_AWS_BATCH_LOG_GROUP=%q\n' "$(tf_output batch_log_group)"
printf 'export TRANSCRIPTFORGE_AWS_WORK_URI=%q\n' "$(tf_output nextflow_work_uri)"
printf 'export TRANSCRIPTFORGE_AWS_REFERENCE_CACHE_URI=%q\n' "$(tf_output reference_cache_uri)"
printf 'export TRANSCRIPTFORGE_AWS_SCIENTIFIC_IMAGE=%q\n' "${scientific_image}"
