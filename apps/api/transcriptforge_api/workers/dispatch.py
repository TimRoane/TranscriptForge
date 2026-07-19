"""API-to-worker dispatch boundary, overridable in integration tests."""

from collections.abc import Callable

from transcriptforge_api.workers.celery_app import (
    prepare_dataset,
    run_analysis,
    run_assay_experiment,
    run_assay_study,
    validate_dataset,
)

ValidationDispatcher = Callable[[str], None]
PreparationDispatcher = Callable[[str], None]
AnalysisDispatcher = Callable[[str], None]
ExperimentDispatcher = Callable[[str], None]
StudyDispatcher = Callable[[str], None]


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


def dispatch_experiment(run_id: str) -> None:
    run_assay_experiment.delay(run_id)


def get_experiment_dispatcher() -> ExperimentDispatcher:
    return dispatch_experiment


def dispatch_study(run_id: str) -> None:
    run_assay_study.delay(run_id)


def get_study_dispatcher() -> StudyDispatcher:
    return dispatch_study
