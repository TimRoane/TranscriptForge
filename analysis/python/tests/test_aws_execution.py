"""Offline tests for the opt-in AWS Batch execution tooling."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_batch_profile_preflight_accepts_digest_pinned_s3_configuration() -> None:
    environment = {
        **os.environ,
        "TRANSCRIPTFORGE_AWS_REGION": "us-west-2",
        "TRANSCRIPTFORGE_AWS_BATCH_QUEUE": "transcriptforge-test",
        "TRANSCRIPTFORGE_AWS_BATCH_JOB_ROLE_ARN": (
            "arn:aws:iam::123456789012:role/transcriptforge-job"
        ),
        "TRANSCRIPTFORGE_AWS_BATCH_LOG_GROUP": "/aws/batch/transcriptforge-test",
        "TRANSCRIPTFORGE_AWS_SCIENTIFIC_IMAGE": (
            "123456789012.dkr.ecr.us-west-2.amazonaws.com/transcriptforge@sha256:"
            + "a" * 64
        ),
        "TRANSCRIPTFORGE_AWS_WORK_URI": "s3://transcriptforge-test/work",
        "TRANSCRIPTFORGE_AWS_REFERENCE_CACHE_URI": (
            "s3://transcriptforge-test/references"
        ),
    }
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/aws/validate_batch_profile.py")],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    result = json.loads(completed.stdout)
    assert result["status"] == "VALID"
    assert result["profile"]["reference_cache_uri"].endswith("/references")


def test_scientific_comparator_reports_exact_and_canonical_matches(tmp_path: Path) -> None:
    local = tmp_path / "local"
    batch = tmp_path / "batch"
    for root in (local, batch):
        (root / "values").mkdir(parents=True)
        (root / "values/counts.tsv").write_text("gene\ts1\ng1\t4\n", encoding="utf-8")
    (local / "values/summary.json").write_text('{"b": 2, "a": 1}\n', encoding="utf-8")
    (batch / "values/summary.json").write_text(
        '{\n  "a": 1,\n  "b": 2\n}\n', encoding="utf-8"
    )
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps(
            {
                "artifacts": [
                    {"path": "values/counts.tsv", "comparison": "sha256"},
                    {"path": "values/summary.json", "comparison": "canonical_json"},
                ]
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/aws/compare_scientific_artifacts.py"),
            str(local),
            str(batch),
            "--contract",
            str(contract),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout)["status"] == "MATCH"
