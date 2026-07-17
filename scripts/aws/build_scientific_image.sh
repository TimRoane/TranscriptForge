#!/usr/bin/env bash
set -euo pipefail

repository_uri="${1:-}"
tag="${2:-$(git rev-parse --short=12 HEAD)}"
if [[ ! "${repository_uri}" =~ ^[0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com/ ]]; then
  echo "Usage: $0 <ECR repository URI> [immutable tag]" >&2
  exit 2
fi

registry="${repository_uri%%/*}"
region="${registry#*.ecr.}"
region="${region%%.*}"
image="${repository_uri}:${tag}"

aws ecr get-login-password --region "${region}" \
  | docker login --username AWS --password-stdin "${registry}"
docker build --target worker --tag "${image}" --file apps/api/Dockerfile .
docker push "${image}"
digest="$(aws ecr describe-images --region "${region}" \
  --repository-name "${repository_uri#*/}" --image-ids "imageTag=${tag}" \
  --query 'imageDetails[0].imageDigest' --output text)"
printf '%s@%s\n' "${repository_uri}" "${digest}"
