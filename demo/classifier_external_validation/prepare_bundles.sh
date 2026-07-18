#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
study_root="${1:-${repo_root}/.transcriptforge-demo/classifier_external_validation}"
downloads="${study_root}/downloads"
python="${repo_root}/.venv/bin/python"

if [[ ! -x "${python}" ]]; then
  echo "TranscriptForge requires the repository .venv Python toolchain." >&2
  exit 1
fi

bash "${repo_root}/demo/classifier_external_validation/download_cohorts.sh" "${downloads}"
docker build \
  --tag transcriptforge/microarray:bioc-3.23 \
  "${repo_root}/containers/microarray"

prepare() {
  local accession="$1"
  local cohort_dir="${study_root}/${accession}"
  if [[ -e "${cohort_dir}" ]]; then
    echo "Refusing to overwrite frozen cohort directory: ${cohort_dir}" >&2
    exit 1
  fi

  "${python}" "${repo_root}/demo/classifier_external_validation/prepare_geo_cohort.py" \
    --accession "${accession}" \
    --raw-tar "${downloads}/${accession}_RAW.tar" \
    --output-dir "${cohort_dir}"

  mkdir -p "${cohort_dir}/rma"
  docker run --rm \
    --volume "${repo_root}:/workspace:ro" \
    --volume "${cohort_dir}:/cohort" \
    transcriptforge/microarray:bioc-3.23 \
    Rscript /workspace/analysis/r/prepare_affymetrix.R \
      --ingestion-manifest /cohort/ingestion_manifest.json \
      --cel-dir /cohort/cel \
      --output-dir /cohort/rma

  "${python}" -m transcriptforge_analysis.microarray_bundle_cli \
    --ingestion-manifest "${cohort_dir}/ingestion_manifest.json" \
    --gene-expression "${cohort_dir}/rma/gene_expression.tsv" \
    --probe-expression "${cohort_dir}/rma/probe_expression.tsv" \
    --gene-feature-metadata "${cohort_dir}/rma/gene_feature_metadata.tsv" \
    --probe-mapping "${cohort_dir}/rma/probe_mapping.tsv" \
    --array-qc-metrics "${cohort_dir}/rma/array_qc_metrics.tsv" \
    --sample-flags "${cohort_dir}/rma/sample_flags.tsv" \
    --array-qc-summary "${cohort_dir}/rma/array_qc_summary.json" \
    --r-output-dir "${cohort_dir}/rma" \
    --metadata "${cohort_dir}/sample_metadata.tsv" \
    --output-dir "${cohort_dir}/bundle" \
    --prepared-dataset-id "${accession,,}-classifier-validation" \
    --prepared-version 1
}

prepare GSE140494
prepare GSE32646

echo "Outcome-separated GPL570 Expression Bundles are available under ${study_root}."
