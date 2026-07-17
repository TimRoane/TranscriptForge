"""Cooperative cancellation for local Nextflow launcher processes."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from contextlib import suppress
from pathlib import Path

CANCELLATION_MARKER_NAME = "cancel.requested"


class RunCancelled(RuntimeError):
    """Raised after a user-requested workflow process has been terminated."""


def cancellation_marker(run_root: Path) -> Path:
    return run_root / CANCELLATION_MARKER_NAME


def request_cancellation(run_root: Path) -> Path:
    """Publish the shared marker observed by the worker launcher."""
    run_root.mkdir(parents=True, exist_ok=True)
    marker = cancellation_marker(run_root)
    temporary = marker.with_name(f".{marker.name}.tmp")
    temporary.write_text("Cancelled by user.\n", encoding="utf-8")
    temporary.replace(marker)
    return marker


def cancellation_requested(run_root: Path) -> bool:
    return cancellation_marker(run_root).is_file()


def raise_if_cancelled(run_root: Path) -> None:
    if cancellation_requested(run_root):
        raise RunCancelled("Cancelled by user.")


def _terminate_process_group(process: subprocess.Popen[str], timeout: float) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def run_cancellable(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    run_root: Path,
    stdout_path: Path,
    stderr_path: Path,
    poll_interval: float = 0.25,
    termination_timeout: float = 10.0,
) -> subprocess.CompletedProcess[str]:
    """Run a command in its own process group while observing a cancel marker."""
    raise_if_cancelled(run_root)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=stdout,
            stderr=stderr,
            text=True,
            start_new_session=True,
        )
        cancelled = False
        while process.poll() is None:
            if cancellation_requested(run_root):
                cancelled = True
                _terminate_process_group(process, termination_timeout)
                break
            time.sleep(poll_interval)
        returncode = process.wait()

    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
    if cancelled or cancellation_requested(run_root):
        raise RunCancelled("Cancelled by user.")
    return subprocess.CompletedProcess(command, returncode, stdout_text, stderr_text)
