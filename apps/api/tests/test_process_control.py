"""Local workflow process cancellation tests."""

import sys
import threading
from pathlib import Path

import pytest
from transcriptforge_api.workers.process_control import (
    RunCancelled,
    request_cancellation,
    run_cancellable,
)


def test_cancellable_process_captures_output(tmp_path: Path) -> None:
    completed = run_cancellable(
        [sys.executable, "-c", "print('finished')"],
        cwd=tmp_path,
        env={},
        run_root=tmp_path,
        stdout_path=tmp_path / "stdout.log",
        stderr_path=tmp_path / "stderr.log",
        poll_interval=0.01,
    )

    assert completed.returncode == 0
    assert completed.stdout == "finished\n"


def test_cancel_marker_terminates_process_group(tmp_path: Path) -> None:
    timer = threading.Timer(0.1, request_cancellation, args=(tmp_path,))
    timer.start()
    try:
        with pytest.raises(RunCancelled, match="Cancelled by user"):
            run_cancellable(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                cwd=tmp_path,
                env={},
                run_root=tmp_path,
                stdout_path=tmp_path / "stdout.log",
                stderr_path=tmp_path / "stderr.log",
                poll_interval=0.01,
                termination_timeout=0.5,
            )
    finally:
        timer.cancel()
