#!/usr/bin/env bash
set -euo pipefail

destination="${1:-.transcriptforge-demo/classifier_external_validation/downloads}"
mkdir -p "${destination}"

download() {
  local accession="$1"
  local series_prefix="$2"
  local expected_sha256="$3"
  local path="${destination}/${accession}_RAW.tar"
  if [[ ! -f "${path}" ]]; then
    curl --fail --location --retry 3 --continue-at - \
      --output "${path}" \
      "https://ftp.ncbi.nlm.nih.gov/geo/series/${series_prefix}/${accession}/suppl/${accession}_RAW.tar"
  fi
  echo "${expected_sha256}  ${path}" | sha256sum --check
}

download \
  GSE140494 \
  GSE140nnn \
  26230bbf9220631a9a7db915115c3d3db72a77b602c4795c03e6b6995a47b47b
download \
  GSE32646 \
  GSE32nnn \
  4e3545310427c9f497350f6b341f7568f9ef302b900c2cdb1c52da05cd2541fc

echo "Frozen raw GPL570 cohorts are available under ${destination}."
