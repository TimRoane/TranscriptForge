"""Celery application and Phase 0 queue smoke task."""

from typing import Any

from celery import Celery  # type: ignore[import-untyped]

from transcriptforge_api import __version__
from transcriptforge_api.config import get_settings
from transcriptforge_api.workers.analysis import run_analysis_workflow
from transcriptforge_api.workers.validation import run_validation_workflow

settings = get_settings()
celery_app = Celery(
    "transcriptforge",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["transcriptforge_api.workers.celery_app"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(name="transcriptforge.system.worker_health")  # type: ignore[untyped-decorator]
def worker_health() -> dict[str, Any]:
    """Prove that a worker can consume a task and return structured JSON."""
    return {
        "status": "ok",
        "service": "transcriptforge-worker",
        "version": __version__,
    }


@celery_app.task(name="transcriptforge.datasets.validate")  # type: ignore[untyped-decorator]
def validate_dataset(run_id: str) -> dict[str, Any]:
    """Execute one already-frozen validation run."""
    return run_validation_workflow(run_id)


@celery_app.task(name="transcriptforge.datasets.prepare")  # type: ignore[untyped-decorator]
def prepare_dataset(run_id: str) -> dict[str, Any]:
    """Execute one already-frozen dataset preparation run."""
    return run_validation_workflow(run_id)


@celery_app.task(name="transcriptforge.analyses.run")  # type: ignore[untyped-decorator]
def run_analysis(run_id: str) -> dict[str, Any]:
    """Execute one already-frozen saved analysis run."""
    return run_analysis_workflow(run_id)
