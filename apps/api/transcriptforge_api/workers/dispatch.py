"""API-to-worker dispatch boundary, overridable in integration tests."""

from collections.abc import Callable

from transcriptforge_api.workers.celery_app import prepare_dataset, run_analysis, validate_dataset

ValidationDispatcher = Callable[[str], None]
PreparationDispatcher = Callable[[str], None]
AnalysisDispatcher = Callable[[str], None]


def dispatch_validation(run_id: str) -> None:
    validate_dataset.delay(run_id)


def get_validation_dispatcher() -> ValidationDispatcher:
    return dispatch_validation


def dispatch_preparation(run_id: str) -> None:
    prepare_dataset.delay(run_id)


def get_preparation_dispatcher() -> PreparationDispatcher:
    return dispatch_preparation


def dispatch_analysis(run_id: str) -> None:
    run_analysis.delay(run_id)


def get_analysis_dispatcher() -> AnalysisDispatcher:
    return dispatch_analysis
