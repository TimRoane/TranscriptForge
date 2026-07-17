#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
demo_root="${repo_root}/.transcriptforge-demo/microarray"
input_dir="${demo_root}/input"
output_dir="${demo_root}/rma-results"
bundle_run_dir="$(mktemp -d "${demo_root}/bundle-results.XXXXXX")"

"${repo_root}/demo/microarray/download_public_demo.sh" "${input_dir}"
mkdir -p "${output_dir}"

docker run --rm \
  --volume "${repo_root}:/workspace:ro" \
  --volume "${input_dir}:/data/cels:ro" \
  --volume "${output_dir}:/data/output" \
  transcriptforge/microarray:bioc-3.23 \
  Rscript /workspace/analysis/r/prepare_affymetrix.R \
    --ingestion-manifest /workspace/demo/microarray/rma_acceptance_manifest.json \
    --cel-dir /data/cels \
    --output-dir /data/output

test -s "${output_dir}/probe_expression.tsv"
test -s "${output_dir}/gene_expression.tsv"
test -s "${output_dir}/probe_mapping.tsv"
test -s "${output_dir}/array_qc_summary.json"

docker compose --project-directory "${repo_root}" run --rm --no-deps \
  --volume "${repo_root}/demo:/app/demo:ro" \
  --volume "${output_dir}:/data/rma:ro" \
  --volume "${bundle_run_dir}:/data/bundle" \
  api \
  python -m transcriptforge_analysis.microarray_bundle_cli \
    --ingestion-manifest /app/demo/microarray/rma_acceptance_manifest.json \
    --gene-expression /data/rma/gene_expression.tsv \
    --probe-expression /data/rma/probe_expression.tsv \
    --gene-feature-metadata /data/rma/gene_feature_metadata.tsv \
    --probe-mapping /data/rma/probe_mapping.tsv \
    --array-qc-metrics /data/rma/array_qc_metrics.tsv \
    --sample-flags /data/rma/sample_flags.tsv \
    --array-qc-summary /data/rma/array_qc_summary.json \
    --r-output-dir /data/rma \
    --metadata /app/demo/microarray/sample_metadata.tsv \
    --output-dir /data/bundle/output \
    --prepared-dataset-id transcriptforge-public-microarray-demo \
    --prepared-version 1

test -s "${bundle_run_dir}/output/bundle_manifest.json"
test -s "${bundle_run_dir}/output/expression_bundle/assays/log_expression.tsv.gz"
test -s "${bundle_run_dir}/output/expression_bundle/assays/probe_expression.tsv.gz"
test -s "${bundle_run_dir}/output/expression_bundle.tar.gz"
test ! -e "${bundle_run_dir}/output/expression_bundle/qc/plots/library_sizes.svg"

docker compose --project-directory "${repo_root}" run --rm --no-deps \
  --volume "${repo_root}/demo:/app/demo:ro" \
  --volume "${bundle_run_dir}/output:/data/bundle:ro" \
  --volume "${bundle_run_dir}:/data/results" \
  worker \
  Rscript /app/analysis/r/differential_expression.R \
    --request /app/demo/microarray/limma_request.json \
    --bundle /data/bundle/expression_bundle.tar.gz \
    --output-dir /data/results/limma-results

python3 "${repo_root}/demo/microarray/check_limma_acceptance.py" \
  "${bundle_run_dir}/limma-results"

echo "Affymetrix RMA acceptance outputs: ${output_dir}"
echo "Canonical Expression Bundle: ${bundle_run_dir}/output"
echo "Paired limma results: ${bundle_run_dir}/limma-results"
