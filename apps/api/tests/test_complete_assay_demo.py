"""Determinism and scientific-truth checks for the complete synthetic demonstration."""

import csv
import json
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest

from demo.assay_development.complete_demo import FEATURE_COUNT, generate_complete_demo
from demo.assay_development.seed_complete import (
    CompleteAssaySeeder,
    SeedConflictError,
    _canonical_sha,
)
from demo.large_experiment.seed import APIClient


def _metadata(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def _counts(path: Path) -> tuple[list[str], np.ndarray]:
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.reader(source, delimiter="\t")
        header = next(reader)
        matrix = np.asarray([[int(value) for value in row[1:]] for row in reader])
    return header[1:], matrix


def test_complete_demo_generation_is_byte_identical_and_balanced(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert generate_complete_demo(first) == generate_complete_demo(second)
    for relative in (
        "generation_manifest.json",
        "synthetic_truth.json",
        "feasibility/counts.tsv",
        "feasibility/sample_metadata.tsv",
        "optimization/counts.tsv",
        "optimization/sample_metadata.tsv",
        "classifier/counts.tsv",
        "classifier/sample_metadata.tsv",
        "precision/counts.tsv",
        "precision/sample_metadata.tsv",
        "robustness/counts.tsv",
        "robustness/sample_metadata.tsv",
    ):
        assert (first / relative).read_bytes() == (second / relative).read_bytes()

    manifest = json.loads((first / "generation_manifest.json").read_text())
    assert manifest["feature_count"] == FEATURE_COUNT
    assert {key: value["measurement_count"] for key, value in manifest["datasets"].items()} == {
        "classifier": 96,
        "feasibility": 18,
        "optimization": 24,
        "precision": 32,
        "robustness": 24,
    }

    classifier = _metadata(first / "classifier/sample_metadata.tsv")
    assert sum(row["outcome"] == "case" for row in classifier) == 48
    for outcome in ("case", "control"):
        subset = [row for row in classifier if row["outcome"] == outcome]
        assert {row["sequencing_run"] for row in subset} == {"run_a", "run_b"}
        assert {row["operator"] for row in subset} == {"operator_1", "operator_2"}
        assert {row["reagent_lot"] for row in subset} == {"lot_a", "lot_b"}

    precision = _metadata(first / "precision/sample_metadata.tsv")
    for biological_id in {row["biological_sample_id"] for row in precision}:
        subset = [row for row in precision if row["biological_sample_id"] == biological_id]
        assert len(subset) == 4
        assert {row["operator"] for row in subset} == {"operator_1", "operator_2"}
        assert {row["run"] for row in subset} == {"run_a", "run_b"}
        assert {row["reagent_lot"] for row in subset} == {"lot_a", "lot_b"}


def test_complete_demo_recovers_prespecified_signal_directions(tmp_path: Path) -> None:
    generate_complete_demo(tmp_path)
    sample_ids, classifier = _counts(tmp_path / "classifier/counts.tsv")
    metadata = {
        row["sample_id"]: row for row in _metadata(tmp_path / "classifier/sample_metadata.tsv")
    }
    cases = [
        index for index, sample in enumerate(sample_ids) if metadata[sample]["outcome"] == "case"
    ]
    controls = [
        index for index, sample in enumerate(sample_ids) if metadata[sample]["outcome"] == "control"
    ]
    log_counts = np.log2(classifier + 1)
    assert float(log_counts[0:40, cases].mean() - log_counts[0:40, controls].mean()) > 0.75
    assert float(log_counts[40:80, cases].mean() - log_counts[40:80, controls].mean()) < -0.65
    assert (
        abs(float(log_counts[1_000:2_000, cases].mean() - log_counts[1_000:2_000, controls].mean()))
        < 0.1
    )

    feasibility_ids, feasibility = _counts(tmp_path / "feasibility/counts.tsv")
    feasibility_metadata = {
        row["sample_id"]: row for row in _metadata(tmp_path / "feasibility/sample_metadata.tsv")
    }
    high = [
        index
        for index, sample in enumerate(feasibility_ids)
        if feasibility_metadata[sample]["input_ng"] == "100"
    ]
    low = [
        index
        for index, sample in enumerate(feasibility_ids)
        if feasibility_metadata[sample]["input_ng"] == "25"
    ]
    feasibility_log = np.log2(feasibility + 1)
    assert float(feasibility_log[80:140, low].mean() - feasibility_log[80:140, high].mean()) < -0.65


class _SeedAPI:
    def __init__(self, analysis: dict[str, Any], runs: list[dict[str, Any]]) -> None:
        self.analysis = analysis
        self.runs = runs
        self.launched = 0

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        del payload
        if method == "GET" and path.endswith("/analyses"):
            return [self.analysis]
        if method == "GET" and path.endswith("/runs"):
            return self.runs
        if method == "POST" and path.endswith("/run"):
            self.launched += 1
            return {"id": "retry-run", "state": "QUEUED"}
        if method == "GET" and path == "/runs/retry-run":
            return {"id": "retry-run", "state": "SUCCEEDED"}
        raise AssertionError(f"Unexpected fake API request: {method} {path}")


def test_complete_seed_resumes_cancelled_analysis_without_duplication(tmp_path: Path) -> None:
    payload = {"analysis_type": "dimension_reduction", "method": "pca"}
    checksum = _canonical_sha(payload)
    api = _SeedAPI(
        {
            "id": "analysis-1",
            "name": "Stable analysis",
            "description": f"Config SHA-256 {checksum}.",
        },
        [{"id": "cancelled-run", "state": "CANCELLED"}],
    )
    seeder = CompleteAssaySeeder(
        cast(APIClient, api),
        tmp_path / "source",
        tmp_path / "summary.json",
        poll_seconds=0,
    )
    analysis = seeder.ensure_analysis("prepared-1", "Stable analysis", payload, "cancel_resume")
    assert analysis["id"] == "analysis-1"
    assert api.launched == 1
    assert seeder.summary["analyses"]["cancel_resume"]["run_id"] == "retry-run"


def test_complete_seed_rejects_stable_name_configuration_conflict(tmp_path: Path) -> None:
    api = _SeedAPI(
        {"id": "analysis-1", "name": "Stable analysis", "description": "different"},
        [],
    )
    seeder = CompleteAssaySeeder(
        cast(APIClient, api), tmp_path / "source", tmp_path / "summary.json"
    )
    with np.testing.assert_raises(SeedConflictError):
        seeder.ensure_analysis(
            "prepared-1",
            "Stable analysis",
            {"analysis_type": "dimension_reduction", "method": "pca"},
            "conflict",
        )


def test_complete_seed_surfaces_worker_failure_details(tmp_path: Path) -> None:
    class FailedAPI:
        def request(
            self, method: str, path: str, payload: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            del method, path, payload
            return {
                "id": "failed-run",
                "state": "FAILED",
                "error_summary": "Synthetic worker failure for acceptance coverage.",
            }

    seeder = CompleteAssaySeeder(
        cast(APIClient, FailedAPI()),
        tmp_path / "source",
        tmp_path / "summary.json",
        poll_seconds=0,
    )
    with pytest.raises(RuntimeError, match=r"failed-run.*Synthetic worker failure"):
        seeder.wait_for_run("failed-run", "failure fixture")
