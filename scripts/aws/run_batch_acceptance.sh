#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
run_id="$(date -u +%Y%m%dT%H%M%SZ)"
acceptance_root="${repo_root}/.transcriptforge-batch-acceptance/${run_id}"
local_results="${acceptance_root}/local-results"
batch_results="${acceptance_root}/batch-results"
work_bucket="${TRANSCRIPTFORGE_AWS_WORK_URI#s3://}"
work_bucket="${work_bucket%%/*}"
batch_result_uri="s3://${work_bucket}/results/batch-acceptance/${run_id}"
batch_work_uri="${TRANSCRIPTFORGE_AWS_WORK_URI%/}/batch-acceptance/${run_id}"

mkdir -p "${acceptance_root}" "${local_results}" "${batch_results}"
python3 "${repo_root}/scripts/aws/validate_batch_profile.py" --live
python3 "${repo_root}/demo/raw_rnaseq/generate.py"
docker compose --project-directory "${repo_root}" build worker

docker compose --project-directory "${repo_root}" run --rm --no-deps \
  -w /acceptance \
  -v "${repo_root}/demo:/app/demo:ro" \
  -v "${repo_root}/analysis:/app/analysis:ro" \
  -v "${repo_root}/pipelines:/app/pipelines:ro" \
  -v "${acceptance_root}:/acceptance" \
  worker nextflow run /app/pipelines/main.nf \
  -entry PREPARE_RAW_RNASEQ -profile test \
  --ingestion_manifest /app/demo/raw_rnaseq/paired/ingestion_manifest.json \
  --reference_definition /app/demo/raw_rnaseq/reference/reference.json \
  --reference_asset_dir /app/demo/raw_rnaseq/reference \
  --reads /app/demo/raw_rnaseq/paired \
  --reference_cache /acceptance/local-reference-cache \
  --prepared_dataset_id fixture-paired-local-v1 \
  --prepared_version 1 \
  --outdir /acceptance/local-results \
  -work-dir /acceptance/local-work \
  -with-trace /acceptance/local-trace.tsv

nextflow run "${repo_root}/pipelines/main.nf" \
  -entry PREPARE_RAW_RNASEQ -profile awsbatch \
  --ingestion_manifest "${repo_root}/demo/raw_rnaseq/paired/ingestion_manifest.json" \
  --reference_definition "${repo_root}/demo/raw_rnaseq/reference/reference.json" \
  --reference_asset_dir "${repo_root}/demo/raw_rnaseq/reference" \
  --reads "${repo_root}/demo/raw_rnaseq/paired" \
  --prepared_dataset_id fixture-paired-batch-v1 \
  --prepared_version 1 \
  --outdir "${batch_result_uri}" \
  -work-dir "${batch_work_uri}" \
  -with-trace "${acceptance_root}/batch-trace.tsv" \
  -with-report "${acceptance_root}/batch-report.html" \
  -with-timeline "${acceptance_root}/batch-timeline.html"

aws s3 sync "${batch_result_uri}" "${batch_results}" --only-show-errors
python3 "${repo_root}/scripts/aws/compare_scientific_artifacts.py" \
  "${local_results}" "${batch_results}" \
  --manifest "${acceptance_root}/scientific-parity.json"

printf 'Acceptance evidence: %s\n' "${acceptance_root}/scientific-parity.json"
printf 'Batch results retained at: %s\n' "${batch_result_uri}"
