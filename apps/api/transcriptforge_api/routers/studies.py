"""Post-lock analytical validation study routes."""

import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from transcriptforge_api.config import Settings, get_settings
from transcriptforge_api.db.session import get_session
from transcriptforge_api.models import (
    Analysis,
    AnalyticalStudy,
    Artifact,
    AssayDevelopmentProject,
    Dataset,
    ModelRecord,
    PreparedDataset,
    Run,
    ValidationResult,
)
from transcriptforge_api.models.enums import RunState
from transcriptforge_api.schemas.studies import (
    LockedModelOption,
    StudyCreate,
    StudyDatasetOption,
    StudyInputOptions,
    StudyRead,
    StudyResultsRead,
    StudyRunRead,
    StudyUpdate,
)
from transcriptforge_api.services import studies as service
from transcriptforge_api.storage import get_storage_backend
from transcriptforge_api.storage.base import StorageBackend
from transcriptforge_api.workers.dispatch import StudyDispatcher, get_study_dispatcher

router = APIRouter(tags=["validation studies"])
Session = Annotated[AsyncSession, Depends(get_session)]
Storage = Annotated[StorageBackend, Depends(get_storage_backend)]
Configuration = Annotated[Settings, Depends(get_settings)]
Dispatcher = Annotated[StudyDispatcher, Depends(get_study_dispatcher)]


async def require_study(session: AsyncSession, study_id: str) -> AnalyticalStudy:
    study = await service.get_study(session, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="Analytical Study not found.")
    return study


@router.get(
    "/assay-projects/{assay_project_id}/study-input-options",
    response_model=StudyInputOptions,
)
async def study_input_options(
    assay_project_id: str, session: Session, storage: Storage
) -> StudyInputOptions:
    assay_project = await session.get(AssayDevelopmentProject, assay_project_id)
    if assay_project is None:
        raise HTTPException(status_code=404, detail="Assay project not found.")
    model_rows = (
        await session.execute(
            select(ModelRecord, Analysis)
            .join(Analysis, ModelRecord.analysis_id == Analysis.id)
            .where(Analysis.project_id == assay_project.project_id, ModelRecord.status == "LOCKED")
            .order_by(ModelRecord.created_at.desc())
        )
    ).all()
    locked_models = []
    for model, _ in model_rows:
        if not model.model_manifest_uri or not model.model_manifest_sha256:
            continue
        manifest = json.loads(storage.read_bytes(model.model_manifest_uri))
        locked_models.append(
            LockedModelOption(
                id=model.id,
                name=model.model_name,
                algorithm=model.algorithm,
                expected_assay=str(manifest["expected_assay"]),
                feature_count=model.feature_count,
                manifest_sha256=model.model_manifest_sha256,
            )
        )
    dataset_rows = (
        await session.execute(
            select(PreparedDataset, Dataset)
            .join(Dataset, PreparedDataset.dataset_id == Dataset.id)
            .where(Dataset.project_id == assay_project.project_id)
            .order_by(Dataset.name, PreparedDataset.version.desc())
        )
    ).all()
    return StudyInputOptions(
        locked_models=locked_models,
        prepared_datasets=[
            StudyDatasetOption(
                id=prepared.id,
                dataset_name=dataset.name,
                version=prepared.version,
                sample_count=prepared.sample_count,
                feature_count=prepared.feature_count,
                assays=list(prepared.value_types_available),
                qc_status=prepared.qc_status,
            )
            for prepared, dataset in dataset_rows
        ],
    )


@router.post("/studies", response_model=StudyRead, status_code=status.HTTP_201_CREATED)
async def create_study(request: StudyCreate, session: Session, storage: Storage) -> StudyRead:
    try:
        study = await service.create_study(session, storage, request)
    except (service.StudyError, KeyError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return service.study_read(study)


@router.get("/assay-projects/{assay_project_id}/studies", response_model=list[StudyRead])
async def list_studies(assay_project_id: str, session: Session) -> list[StudyRead]:
    return [
        service.study_read(study) for study in await service.list_studies(session, assay_project_id)
    ]


@router.get("/studies/{study_id}", response_model=StudyRead)
async def get_study(study_id: str, session: Session) -> StudyRead:
    return service.study_read(await require_study(session, study_id))


@router.patch("/studies/{study_id}", response_model=StudyRead)
async def update_study(
    study_id: str,
    request: StudyUpdate,
    session: Session,
    storage: Storage,
) -> StudyRead:
    study = await require_study(session, study_id)
    try:
        updated = await service.update_study(session, storage, study, request)
    except (service.StudyError, ValueError, KeyError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return service.study_read(updated)


@router.post("/studies/{study_id}/validate-design", response_model=StudyRead)
async def validate_study_design(study_id: str, session: Session, storage: Storage) -> StudyRead:
    study = await require_study(session, study_id)
    try:
        updated = await service.update_study(session, storage, study, StudyUpdate())
    except (service.StudyError, ValueError, KeyError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return service.study_read(updated)


@router.post("/studies/{study_id}/lock", response_model=StudyRead)
async def lock_study(study_id: str, session: Session, storage: Storage) -> StudyRead:
    study = await require_study(session, study_id)
    try:
        locked = await service.lock_study(session, storage, study)
    except service.StudyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return service.study_read(locked)


@router.post(
    "/studies/{study_id}/run",
    response_model=StudyRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_study(
    study_id: str,
    session: Session,
    storage: Storage,
    settings: Configuration,
    dispatch: Dispatcher,
) -> StudyRunRead:
    if not settings.assay_study_execution_enabled:
        raise HTTPException(status_code=409, detail="Analytical Study execution is disabled.")
    study = await require_study(session, study_id)
    try:
        run = await service.create_study_run(
            session, storage, study, profile=settings.nextflow_profile
        )
    except service.StudyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    try:
        await run_in_threadpool(dispatch, run.id)
    except Exception as error:
        run.state = RunState.FAILED.value
        run.error_summary = "The Analytical Study task could not be queued."
        run.finished_at = datetime.now(UTC)
        study.status = "FAILED"
        await session.commit()
        raise HTTPException(
            status_code=503, detail="The study worker queue is unavailable."
        ) from error
    return StudyRunRead(study=service.study_read(study), run_id=run.id, run_state="QUEUED")


@router.post(
    "/studies/{study_id}/clone", response_model=StudyRead, status_code=status.HTTP_201_CREATED
)
async def clone_study(study_id: str, session: Session) -> StudyRead:
    source = await require_study(session, study_id)
    return service.study_read(await service.clone_study(session, source))


@router.get("/studies/{study_id}/results", response_model=StudyResultsRead)
async def study_results(study_id: str, session: Session) -> StudyResultsRead:
    study = await require_study(session, study_id)
    run = await session.scalar(
        select(Run).where(Run.study_id == study.id).order_by(Run.created_at.desc()).limit(1)
    )
    if run is None:
        return StudyResultsRead(
            study_id=study.id, status=study.status, run_id=None, summary=None, artifacts=[]
        )
    result = await session.scalar(select(ValidationResult).where(ValidationResult.run_id == run.id))
    artifacts = list(
        await session.scalars(
            select(Artifact).where(Artifact.run_id == run.id).order_by(Artifact.display_order)
        )
    )
    return StudyResultsRead(
        study_id=study.id,
        status=study.status,
        run_id=run.id,
        summary=result.summary_json if result else None,
        artifacts=[
            {
                "id": artifact.id,
                "artifact_type": artifact.artifact_type,
                "title": artifact.title,
                "relative_path": artifact.relative_path,
                "mime_type": artifact.mime_type,
                "size_bytes": artifact.size_bytes,
                "sha256": artifact.sha256,
            }
            for artifact in artifacts
        ],
    )
