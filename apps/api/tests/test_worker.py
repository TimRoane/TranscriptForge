"""Worker task contract tests."""

from pathlib import Path

from transcriptforge_api.config import Settings
from transcriptforge_api.workers.analysis import _artifact_specs
from transcriptforge_api.workers.celery_app import worker_health
from transcriptforge_api.workers.validation import RunSnapshot, build_nextflow_command


def test_worker_health_payload() -> None:
    assert worker_health.run() == {
        "status": "ok",
        "service": "transcriptforge-worker",
        "version": "0.1.0",
    }


def test_nextflow_command_is_an_argument_array(tmp_path: Path) -> None:
    settings = Settings(
        nextflow_executable="nextflow-test",
        pipeline_path=tmp_path / "main.nf",
    )
    snapshot = RunSnapshot("run-1", "dataset-1", "local://params.json", "test")
    command = build_nextflow_command(
        settings,
        snapshot,
        tmp_path / "params.json",
        tmp_path / "work",
        tmp_path / "provenance",
        "tf_run_1",
    )

    assert command[:4] == [
        "nextflow-test",
        "run",
        str((tmp_path / "main.nf").resolve()),
        "-entry",
    ]
    assert command[command.index("-profile") + 1] == "test"
    assert command[command.index("-params-file") + 1] == str(tmp_path / "params.json")


def test_awsbatch_command_uses_run_isolated_s3_work_prefix(tmp_path: Path) -> None:
    settings = Settings(
        nextflow_executable="nextflow-test",
        pipeline_path=tmp_path / "main.nf",
        aws_work_uri="s3://transcriptforge/work",
    )
    snapshot = RunSnapshot("run-1", "dataset-1", "local://params.json", "awsbatch")

    command = build_nextflow_command(
        settings,
        snapshot,
        tmp_path / "params.json",
        tmp_path / "local-work",
        tmp_path / "provenance",
        "tf_run_1",
    )

    assert command[command.index("-work-dir") + 1] == ("s3://transcriptforge/work/runs/run-1")


def test_signature_outputs_are_indexed_as_analysis_artifacts(tmp_path: Path) -> None:
    results = tmp_path / "output" / "analysis" / "results"
    results.mkdir(parents=True)
    for name in (
        "signature_scores.json",
        "signature_scores.tsv",
        "scored_features.tsv",
        "signature_scores.svg",
    ):
        (results / name).write_text("test\n", encoding="utf-8")

    artifacts = {item.artifact_type: item for item in _artifact_specs(tmp_path)}

    assert artifacts["signature_scores"].mime_type == "application/json"
    assert artifacts["signature_scores_table"].mime_type == "text/tab-separated-values"
    assert artifacts["signature_scored_features"].title == "Final scored signature features"
    assert artifacts["signature_scores_svg"].mime_type == "image/svg+xml"
