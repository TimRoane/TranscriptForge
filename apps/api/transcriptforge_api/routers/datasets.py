"""Dataset CRUD, upload, ingestion, and validation routes."""

import json
from datetime import UTC, datetime
from io import BytesIO
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from transcriptforge_api.config import Settings, get_settings
from transcriptforge_api.db.session import get_session
from transcriptforge_api.models import Dataset, DatasetFile, PreparedDataset, Run
from transcriptforge_api.models.enums import DatasetSourceKind, DatasetStatus, RunState
from transcriptforge_api.routers.projects import require_project
from transcriptforge_api.schemas.datasets import (
    UPLOAD_ROLE_COMPATIBILITY,
    DatasetCreate,
    DatasetFileRead,
    DatasetFileRole,
    DatasetRead,
    DatasetUpdate,
    MicroarrayIngestionRead,
    MicroarrayIngestionRequest,
    MicroarrayPlatformCatalogRead,
    PreparedDatasetRead,
    RawRNASeqIngestionRead,
    RawRNASeqIngestionRequest,
    ReferenceBundleCatalogRead,
)
from transcriptforge_api.schemas.runs import DatasetValidationRequest, RunRead
from transcriptforge_api.services import datasets as dataset_service
from transcriptforge_api.services import microarray as microarray_service
from transcriptforge_api.services import raw_rnaseq as raw_rnaseq_service
from transcriptforge_api.services import runs as run_service
from transcriptforge_api.storage import get_storage_backend
from transcriptforge_api.storage.base import StorageBackend
from transcriptforge_api.workers.dispatch import (
    PreparationDispatcher,
    ValidationDispatcher,
    get_preparation_dispatcher,
    get_validation_dispatcher,
)

router = APIRouter(tags=["datasets"])
Session = Annotated[AsyncSession, Depends(get_session)]
Storage = Annotated[StorageBackend, Depends(get_storage_backend)]
Configuration = Annotated[Settings, Depends(get_settings)]
Dispatcher = Annotated[ValidationDispatcher, Depends(get_validation_dispatcher)]
PrepareDispatcher = Annotated[PreparationDispatcher, Depends(get_preparation_dispatcher)]


async def require_dataset(session: AsyncSession, dataset_id: str) -> Dataset:
    dataset = await dataset_service.get_dataset(session, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    return dataset


@router.post(
    "/projects/{project_id}/datasets",
    response_model=DatasetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_dataset(project_id: str, request: DatasetCreate, session: Session) -> Dataset:
    await require_project(session, project_id)
    return await dataset_service.create_dataset(session, project_id, request)


@router.get("/projects/{project_id}/datasets", response_model=list[DatasetRead])
async def list_datasets(project_id: str, session: Session) -> list[Dataset]:
    await require_project(session, project_id)
    return await dataset_service.list_datasets(session, project_id)


@router.get("/datasets/{dataset_id}", response_model=DatasetRead)
async def get_dataset(dataset_id: str, session: Session) -> Dataset:
    return await require_dataset(session, dataset_id)


@router.get("/reference-bundles", response_model=list[ReferenceBundleCatalogRead])
async def list_reference_bundles() -> list[dict[str, Any]]:
    return raw_rnaseq_service.list_reference_bundles()


@router.get("/microarray-platforms", response_model=list[MicroarrayPlatformCatalogRead])
async def list_microarray_platforms() -> list[dict[str, Any]]:
    return microarray_service.list_platform_adapters()


@router.get("/datasets/{dataset_id}/files", response_model=list[DatasetFileRead])
async def list_dataset_files(dataset_id: str, session: Session) -> list[DatasetFile]:
    await require_dataset(session, dataset_id)
    return await dataset_service.list_dataset_files(session, dataset_id)


@router.patch("/datasets/{dataset_id}", response_model=DatasetRead)
async def update_dataset(
    dataset_id: str, request: DatasetUpdate, session: Session
) -> Dataset:
    dataset = await require_dataset(session, dataset_id)
    dataset.status = DatasetStatus.DRAFT.value
    return await dataset_service.update_dataset(session, dataset, request)


@router.delete("/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(dataset_id: str, session: Session) -> Response:
    dataset = await require_dataset(session, dataset_id)
    await dataset_service.delete_dataset(session, dataset)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/datasets/{dataset_id}/files",
    response_model=DatasetFileRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dataset_file(
    dataset_id: str,
    session: Session,
    storage: Storage,
    settings: Configuration,
    role: Annotated[DatasetFileRole, Form()],
    file: Annotated[UploadFile, File()],
) -> DatasetFile:
    dataset = await require_dataset(session, dataset_id)
    allowed_roles = UPLOAD_ROLE_COMPATIBILITY[DatasetSourceKind(dataset.source_kind)]
    if role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"File role '{role.value}' is incompatible with source kind "
                f"'{dataset.source_kind}'."
            ),
        )
    upload_size = file.size
    if upload_size is None:
        upload_size = await run_in_threadpool(file.file.seek, 0, 2)
        await run_in_threadpool(file.file.seek, 0)
    if upload_size > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Upload exceeds the configured {settings.max_upload_bytes}-byte file limit.",
        )
    used_bytes = await dataset_service.project_dataset_upload_bytes(session, dataset.project_id)
    if used_bytes + upload_size > settings.project_upload_quota_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                "Upload would exceed the configured project dataset-input quota "
                f"of {settings.project_upload_quota_bytes} bytes."
            ),
        )
    dataset.status = DatasetStatus.DRAFT.value
    original_name = file.filename or "upload"
    namespace = ("projects", dataset.project_id, "datasets", dataset.id, "inputs")
    stored = await run_in_threadpool(storage.put, namespace, original_name, file.file)
    try:
        return await dataset_service.create_dataset_file(
            session, dataset.id, role, original_name, stored
        )
    except Exception:
        await run_in_threadpool(storage.delete, stored.uri)
        raise


@router.post(
    "/datasets/{dataset_id}/raw-rnaseq/ingest",
    response_model=RawRNASeqIngestionRead,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_raw_rnaseq_dataset(
    dataset_id: str,
    request: RawRNASeqIngestionRequest,
    session: Session,
    storage: Storage,
) -> dict[str, Any]:
    dataset = await require_dataset(session, dataset_id)
    try:
        manifest = await raw_rnaseq_service.build_ingestion_manifest(
            session, storage, dataset, request
        )
    except raw_rnaseq_service.RawRNASeqIngestionError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    namespace = ("projects", dataset.project_id, "datasets", dataset.id, "inputs")
    stored = await run_in_threadpool(
        storage.put, namespace, "raw-rnaseq-ingestion.json", BytesIO(payload)
    )
    dataset.status = DatasetStatus.VALID.value
    dataset.annotation_release = str(manifest["reference"]["annotation_release"])
    try:
        await dataset_service.create_dataset_file(
            session,
            dataset.id,
            DatasetFileRole.RAW_INGESTION_MANIFEST,
            "raw-rnaseq-ingestion.json",
            stored,
        )
    except Exception:
        await run_in_threadpool(storage.delete, stored.uri)
        raise
    return manifest


@router.get(
    "/datasets/{dataset_id}/raw-rnaseq/ingestion",
    response_model=RawRNASeqIngestionRead | None,
)
async def get_raw_rnaseq_ingestion(
    dataset_id: str, session: Session, storage: Storage
) -> dict[str, Any] | None:
    await require_dataset(session, dataset_id)
    inputs = await dataset_service.list_dataset_files(session, dataset_id)
    relevant_roles = {
        DatasetFileRole.RAW_INGESTION_MANIFEST.value,
        DatasetFileRole.SAMPLE_SHEET.value,
        DatasetFileRole.FASTQ_R1.value,
        DatasetFileRole.FASTQ_R2.value,
    }
    latest_relevant = next((item for item in inputs if item.role in relevant_roles), None)
    ingestion = (
        latest_relevant
        if latest_relevant is not None
        and latest_relevant.role == DatasetFileRole.RAW_INGESTION_MANIFEST.value
        else None
    )
    if ingestion is None:
        return None
    manifest = dict(
        json.loads(await run_in_threadpool(storage.read_bytes, ingestion.storage_uri))
    )
    try:
        _, definition_sha256 = raw_rnaseq_service.load_reference_bundle(
            str(manifest["reference"]["reference_id"])
        )
    except raw_rnaseq_service.RawRNASeqIngestionError:
        return None
    if definition_sha256 != manifest["reference"]["definition_sha256"]:
        return None
    return manifest


@router.post(
    "/datasets/{dataset_id}/microarray/ingest",
    response_model=MicroarrayIngestionRead,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_microarray_dataset(
    dataset_id: str,
    request: MicroarrayIngestionRequest,
    session: Session,
    storage: Storage,
) -> dict[str, Any]:
    dataset = await require_dataset(session, dataset_id)
    try:
        manifest = await microarray_service.build_ingestion_manifest(
            session, storage, dataset, request
        )
    except microarray_service.MicroarrayIngestionError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    namespace = ("projects", dataset.project_id, "datasets", dataset.id, "inputs")
    stored = await run_in_threadpool(
        storage.put, namespace, "microarray-ingestion.json", BytesIO(payload)
    )
    dataset.status = DatasetStatus.VALID.value
    dataset.annotation_release = str(manifest["platform"]["annotation"]["package"])
    try:
        await dataset_service.create_dataset_file(
            session,
            dataset.id,
            DatasetFileRole.MICROARRAY_INGESTION_MANIFEST,
            "microarray-ingestion.json",
            stored,
        )
    except Exception:
        await run_in_threadpool(storage.delete, stored.uri)
        raise
    return manifest


@router.get(
    "/datasets/{dataset_id}/microarray/ingestion",
    response_model=MicroarrayIngestionRead | None,
)
async def get_microarray_ingestion(
    dataset_id: str, session: Session, storage: Storage
) -> dict[str, Any] | None:
    await require_dataset(session, dataset_id)
    inputs = await dataset_service.list_dataset_files(session, dataset_id)
    relevant_roles = {
        DatasetFileRole.MICROARRAY_INGESTION_MANIFEST.value,
        DatasetFileRole.SAMPLE_METADATA.value,
        DatasetFileRole.CEL_FILE.value,
    }
    latest_relevant = next((item for item in inputs if item.role in relevant_roles), None)
    ingestion = (
        latest_relevant
        if latest_relevant is not None
        and latest_relevant.role == DatasetFileRole.MICROARRAY_INGESTION_MANIFEST.value
        else None
    )
    if ingestion is None:
        return None
    manifest = dict(
        json.loads(await run_in_threadpool(storage.read_bytes, ingestion.storage_uri))
    )
    try:
        _, definition_sha256 = microarray_service.load_platform_adapter(
            str(manifest["platform"]["platform_id"])
        )
    except (KeyError, microarray_service.MicroarrayIngestionError):
        return None
    if definition_sha256 != manifest["platform"]["definition_sha256"]:
        return None
    return manifest


@router.post(
    "/datasets/{dataset_id}/validate",
    response_model=RunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def validate_dataset(
    dataset_id: str,
    request: DatasetValidationRequest,
    session: Session,
    storage: Storage,
    settings: Configuration,
    dispatch: Dispatcher,
) -> Run:
    dataset = await require_dataset(session, dataset_id)
    previous_status = dataset.status
    try:
        validation_run = await run_service.create_validation_run(
            session,
            storage,
            dataset,
            request,
            profile=settings.nextflow_profile,
        )
    except run_service.ValidationInputError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    try:
        await run_in_threadpool(dispatch, validation_run.id)
    except Exception as error:
        validation_run.state = RunState.FAILED.value
        validation_run.error_summary = "The validation task could not be queued."
        validation_run.finished_at = datetime.now(UTC)
        dataset.status = previous_status
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The validation worker queue is unavailable.",
        ) from error
    return validation_run


@router.get("/datasets/{dataset_id}/validation-runs", response_model=list[RunRead])
async def list_dataset_validation_runs(dataset_id: str, session: Session) -> list[Run]:
    await require_dataset(session, dataset_id)
    return await run_service.list_validation_runs(session, dataset_id)


@router.post(
    "/datasets/{dataset_id}/prepare",
    response_model=RunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def prepare_dataset(
    dataset_id: str,
    session: Session,
    storage: Storage,
    settings: Configuration,
    dispatch: PrepareDispatcher,
) -> Run:
    dataset = await require_dataset(session, dataset_id)
    previous_status = dataset.status
    try:
        preparation_run = await run_service.create_preparation_run(
            session,
            storage,
            dataset,
            profile=settings.nextflow_profile,
        )
    except run_service.ValidationInputError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    try:
        await run_in_threadpool(dispatch, preparation_run.id)
    except Exception as error:
        preparation_run.state = RunState.FAILED.value
        preparation_run.error_summary = "The preparation task could not be queued."
        preparation_run.finished_at = datetime.now(UTC)
        dataset.status = previous_status
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The preparation worker queue is unavailable.",
        ) from error
    return preparation_run


@router.get("/datasets/{dataset_id}/preparation-runs", response_model=list[RunRead])
async def list_dataset_preparation_runs(dataset_id: str, session: Session) -> list[Run]:
    await require_dataset(session, dataset_id)
    return await run_service.list_preparation_runs(session, dataset_id)


@router.get(
    "/datasets/{dataset_id}/prepared-versions",
    response_model=list[PreparedDatasetRead],
)
async def list_prepared_versions(
    dataset_id: str, session: Session
) -> list[PreparedDataset]:
    await require_dataset(session, dataset_id)
    return await run_service.list_prepared_datasets(session, dataset_id)


@router.get(
    "/prepared-datasets/{prepared_dataset_id}",
    response_model=PreparedDatasetRead,
)
async def get_prepared_dataset(
    prepared_dataset_id: str, session: Session
) -> PreparedDataset:
    prepared = await run_service.get_prepared_dataset(session, prepared_dataset_id)
    if prepared is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prepared dataset not found.",
        )
    return prepared
