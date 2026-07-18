#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${root}"

output="docs/demo/transcriptforge-walkthrough.mp4"
arguments=(
  -f concat -safe 0 -i docs/demo/slides.txt
  -vf "scale=1440:1120:force_original_aspect_ratio=decrease,pad=1440:1120:(ow-iw)/2:(oh-ih)/2:color=white,format=yuv420p"
  -r 30 -c:v libx264 -preset medium -crf 24 -movflags +faststart -y "${output}"
)

if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg "${arguments[@]}"
else
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    --volume "${root}:/work" \
    --workdir /work \
    jrottenberg/ffmpeg:7.1-alpine@sha256:8ec1ee1f6a0fcd37c97725827b6b7832795c9596e3439b8da56d7700d61ae778 \
    "${arguments[@]}"
fi

echo "Wrote ${output}"
