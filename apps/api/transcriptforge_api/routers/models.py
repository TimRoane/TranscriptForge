"""Classifier model registry lifecycle routes."""

from collections.abc import Awaitable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api.db.session import get_session
from transcriptforge_api.models import ModelRecord
from transcriptforge_api.schemas.models import (
    ModelDecisionRequest,
    ModelIntegrityRead,
    ModelLockReadinessRead,
    ModelRecordRead,
)
from transcriptforge_api.services import models as service
from transcriptforge_api.storage import get_storage_backend
from transcriptforge_api.storage.base import StorageBackend

router = APIRouter(tags=["models"])
Session = Annotated[AsyncSession, Depends(get_session)]
Storage = Annotated[StorageBackend, Depends(get_storage_backend)]


async def require_model(session: AsyncSession, model_id: str) -> ModelRecord:
    model = await service.get_model(session, model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found.")
    return model


@router.get("/analyses/{analysis_id}/models", response_model=list[ModelRecordRead])
async def list_models(analysis_id: str, session: Session) -> list[ModelRecord]:
    return await service.list_models(session, analysis_id)


@router.get("/models/{model_id}", response_model=ModelRecordRead)
async def get_model(model_id: str, session: Session) -> ModelRecord:
    return await require_model(session, model_id)


@router.get("/models/{model_id}/lock-readiness", response_model=ModelLockReadinessRead)
async def lock_readiness(
    model_id: str, session: Session, storage: Storage
) -> ModelLockReadinessRead:
    return await service.lock_readiness(session, storage, await require_model(session, model_id))


async def _transition(operation: Awaitable[ModelRecord]) -> ModelRecord:
    try:
        return await operation
    except service.ModelLifecycleError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/models/{model_id}/review", response_model=ModelRecordRead)
async def review_model(
    model_id: str, request: ModelDecisionRequest, session: Session, storage: Storage
) -> ModelRecord:
    return await _transition(
        service.review_model(
            session, storage, await require_model(session, model_id), request.rationale
        )
    )


@router.post("/models/{model_id}/lock", response_model=ModelRecordRead)
async def lock_model(
    model_id: str, request: ModelDecisionRequest, session: Session, storage: Storage
) -> ModelRecord:
    return await _transition(
        service.lock_model(
            session, storage, await require_model(session, model_id), request.rationale
        )
    )


@router.post(
    "/models/{model_id}/clone", response_model=ModelRecordRead, status_code=status.HTTP_201_CREATED
)
async def clone_model(model_id: str, session: Session, storage: Storage) -> ModelRecord:
    return await service.clone_model(session, storage, await require_model(session, model_id))


@router.post("/models/{model_id}/retire", response_model=ModelRecordRead)
async def retire_model(
    model_id: str, request: ModelDecisionRequest, session: Session
) -> ModelRecord:
    return await _transition(
        service.retire_model(session, await require_model(session, model_id), request.rationale)
    )


@router.post("/models/{model_id}/integrity", response_model=ModelIntegrityRead)
async def check_integrity(model_id: str, session: Session, storage: Storage) -> ModelIntegrityRead:
    return await service.integrity(session, storage, await require_model(session, model_id))


@router.get("/models/{model_id}/manifest")
async def download_manifest(model_id: str, session: Session, storage: Storage) -> Response:
    model = await require_model(session, model_id)
    if not model.model_manifest_uri:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Model is not locked.")
    return Response(
        storage.read_bytes(model.model_manifest_uri),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="model_manifest.json"'},
    )


@router.get("/models/{model_id}/package")
async def download_package(model_id: str, session: Session, storage: Storage) -> Response:
    model = await require_model(session, model_id)
    if not model.model_package_uri:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Model is not locked.")
    return Response(
        storage.read_bytes(model.model_package_uri),
        media_type="application/gzip",
        headers={"Content-Disposition": 'attachment; filename="locked_model_package.tar.gz"'},
    )
