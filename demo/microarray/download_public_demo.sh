#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
destination="${1:-${script_dir}/data}"
mkdir -p "${destination}"

download() {
  local url="$1"
  local name="$2"
  local sha256="$3"
  if [[ ! -f "${destination}/${name}" ]]; then
    curl --fail --location --retry 3 --output "${destination}/${name}" "${url}"
  fi
  echo "${sha256}  ${destination}/${name}" | sha256sum --check
}

download \
  "https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM979nnn/GSM979412/suppl/GSM979412_71D.CEL.gz" \
  "GSM979412_71D.CEL.gz" \
  "50dcc4031fcfd062899e28f7f9b5138b0f6b290dcca37ebd6493d0561cc3d176"
download \
  "https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM979nnn/GSM979414/suppl/GSM979414_71S.CEL.gz" \
  "GSM979414_71S.CEL.gz" \
  "5ae7681a7007988d8b6d09fcb03b0b7e5d93691ce6244a4c25ab43a44d934428"
download \
  "https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM979nnn/GSM979415/suppl/GSM979415_77D.CEL.gz" \
  "GSM979415_77D.CEL.gz" \
  "f13905cbe198e21f95feeceafa49afa133fa7ee101f0fd69da96730c963fc40d"
download \
  "https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM979nnn/GSM979417/suppl/GSM979417_77S.CEL.gz" \
  "GSM979417_77S.CEL.gz" \
  "9ae43fd061776e7f19cf608851511a3da3cf89fa9519134d6f89584722dbc996"
download \
  "https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM979nnn/GSM979418/suppl/GSM979418_91D.CEL.gz" \
  "GSM979418_91D.CEL.gz" \
  "a172b9d985c82f2e92021668e3c13c64eea04bbf72ebec9318fdbd1cebd59eb3"
download \
  "https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM979nnn/GSM979420/suppl/GSM979420_91S.CEL.gz" \
  "GSM979420_91S.CEL.gz" \
  "8d4d93d2d3a7a4df1d53955011025dc65c52b205f743667acc536a7c4082433c"
download \
  "https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM979nnn/GSM979421/suppl/GSM979421_93D.CEL.gz" \
  "GSM979421_93D.CEL.gz" \
  "b4d11088cbbb96feaf40ca2ff83082fcce3186ca0c95ab44d71d5a17e246276a"
download \
  "https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM979nnn/GSM979423/suppl/GSM979423_93S.CEL.gz" \
  "GSM979423_93S.CEL.gz" \
  "1758f03ded2a161c8731f8b65d247c97f5cee4d4006854cc31fba478fd14a7b5"

install -m 0644 "${script_dir}/sample_metadata.tsv" "${destination}/sample_metadata.tsv"
echo "Public GPL6244 demo materialized at ${destination}"
