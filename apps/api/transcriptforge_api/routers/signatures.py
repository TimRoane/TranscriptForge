"""Candidate gene signature draft routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from transcriptforge_api.db.session import get_session
from transcriptforge_api.models import GeneSignature, Project
from transcriptforge_api.schemas.signatures import GeneSignatureCreate, GeneSignatureRead
from transcriptforge_api.services import runs as run_service
from transcriptforge_api.services import signatures as signature_service
from transcriptforge_api.storage import get_storage_backend
from transcriptforge_api.storage.base import StorageBackend

router = APIRouter(tags=["signatures"])
Session = Annotated[AsyncSession, Depends(get_session)]
Storage = Annotated[StorageBackend, Depends(get_storage_backend)]


@router.post(
    "/runs/{run_id}/signatures",
    response_model=GeneSignatureRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_signature(
    run_id: str,
    request: GeneSignatureCreate,
    session: Session,
    storage: Storage,
) -> GeneSignature:
    run = await run_service.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    artifact = await run_service.get_artifact_by_type(
        session, run_id, "differential_expression_results"
    )
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The source run does not have differential-expression results.",
        )
    payload = await run_in_threadpool(storage.read_bytes, artifact.storage_uri)
    try:
        return await signature_service.create_signature(session, run, artifact, payload, request)
    except signature_service.SignatureInputError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("/runs/{run_id}/signatures", response_model=list[GeneSignatureRead])
async def list_run_signatures(run_id: str, session: Session) -> list[GeneSignature]:
    if await run_service.get_run(session, run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    return await signature_service.list_run_signatures(session, run_id)


@router.get("/projects/{project_id}/signatures", response_model=list[GeneSignatureRead])
async def list_project_signatures(project_id: str, session: Session) -> list[GeneSignature]:
    if await session.get(Project, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return await signature_service.list_project_signatures(session, project_id)


@router.get("/signatures/{signature_id}", response_model=GeneSignatureRead)
async def get_signature(signature_id: str, session: Session) -> GeneSignature:
    signature = await signature_service.get_signature(session, signature_id)
    if signature is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signature not found.")
    return signature
