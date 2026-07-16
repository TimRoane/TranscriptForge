"""Worker task contract tests."""

from pathlib import Path

from transcriptforge_api.config import Settings
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
