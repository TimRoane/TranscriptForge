#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
acceptance_root="${repo_root}/.transcriptforge-raw-acceptance"
mkdir -p "${acceptance_root}/paired-session" "${acceptance_root}/single-session"

run_workflow() {
  local layout="$1"
  local resume_flag="${2:-}"
  docker compose --project-directory "${repo_root}" run --rm --no-deps \
    -w "/acceptance/${layout}-session" \
    -v "${repo_root}/demo:/app/demo:ro" \
    -v "${repo_root}/analysis:/app/analysis:ro" \
    -v "${repo_root}/pipelines:/app/pipelines:ro" \
    -v "${acceptance_root}:/acceptance" \
    worker nextflow run /app/pipelines/main.nf \
    -entry PREPARE_RAW_RNASEQ -profile test ${resume_flag} \
    --ingestion_manifest "/app/demo/raw_rnaseq/${layout}/ingestion_manifest.json" \
    --reference_definition /app/demo/raw_rnaseq/reference/reference.json \
    --reference_asset_dir /app/demo/raw_rnaseq/reference \
    --reads "/app/demo/raw_rnaseq/${layout}" \
    --reference_cache /acceptance/reference-cache \
    --prepared_dataset_id "fixture-${layout}-v1" \
    --prepared_version 1 \
    --outdir "/acceptance/${layout}-results" \
    -work-dir "/acceptance/${layout}-work" \
    -with-trace "/acceptance/${layout}-trace.tsv"
}

python3 "${repo_root}/demo/raw_rnaseq/generate.py"
if [[ "${TRANSCRIPTFORGE_SKIP_WORKER_BUILD:-0}" != "1" ]]; then
  docker compose --project-directory "${repo_root}" build worker
fi
run_workflow paired
run_workflow paired -resume
run_workflow single

python3 - "${acceptance_root}" <<'PY'
import csv
import json
import sys
import tarfile
from pathlib import Path

root = Path(sys.argv[1])
expected = {
    "ENSGFIX000001": [24, 22, 5, 6],
    "ENSGFIX000002": [5, 6, 24, 22],
    "ENSGFIX000003": [12, 13, 12, 13],
    "ENSGFIX000004": [8, 8, 8, 8],
}
for layout in ("paired", "single"):
    result = root / f"{layout}-results"
    with (result / "raw-rnaseq/quantification/gene_counts.tsv").open() as source:
        rows = list(csv.reader(source, delimiter="\t"))
    observed = {row[0]: [int(value) for value in row[1:]] for row in rows[1:]}
    assert observed == expected, (layout, observed)
    manifest = json.loads(
        (result / "preparation/prepared/bundle_manifest.json").read_text()
    )
    assert [item["name"] for item in manifest["assays"]] == [
        "raw_counts",
        "log_expression",
        "tpm",
        "transcript_abundance",
    ]
    assert manifest["assays"][-1]["feature_level"] == "transcript"
    with (result / "raw-rnaseq/quantification/transcript_counts.tsv").open() as source:
        transcript_rows = list(csv.reader(source, delimiter="\t"))
    observed_transcripts = {
        row[0]: [round(float(value)) for value in row[1:]]
        for row in transcript_rows[1:]
    }
    assert observed_transcripts == {
        gene.replace("ENSG", "ENST"): values for gene, values in expected.items()
    }
    qc = json.loads(
        (result / "raw-rnaseq/quantification/raw_rnaseq_qc_summary.json").read_text()
    )
    assert qc["mitochondrial_metrics_available"] is True
    assert qc["ribosomal_metrics_available"] is True
    assert qc["sample_count"] == 4
    with tarfile.open(
        result / "raw-rnaseq/quantification/salmon_quantifications.tar.gz", "r:gz"
    ) as archive:
        assert len([name for name in archive.getnames() if name.endswith("/quant.sf")]) == 4
    assert (result / "raw-rnaseq/multiqc/multiqc_report.html").stat().st_size > 100_000

paired_execution = json.loads(
    (root / "paired-results/raw-rnaseq/provenance/verified/execution_manifest.json").read_text()
)
assert paired_execution["lane_count"] == 8
assert all(sample["lane_count"] == 2 for sample in paired_execution["samples"])

single_reference = json.loads(
    (root / "single-results/raw-rnaseq/reference/reference_materialization.json").read_text()
)
assert single_reference["cache_hit"] is True
assert single_reference["salmon_version"] == "1.11.4"

trace = (root / "paired-trace.tsv").read_text()
assert trace.count("\tCACHED\t") >= 17
print("Raw RNA-seq paired, single-end, shared-index, and resume acceptance passed.")
PY
