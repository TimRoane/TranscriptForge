"""Import and browse immutable external classifier validation studies."""

from io import BytesIO
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from transcriptforge_api.db.session import get_session
from transcriptforge_api.models import ClassifierExternalValidation, Project
from transcriptforge_api.models.base import new_id
from transcriptforge_api.schemas.external_validations import (
    ClassifierExternalValidationImport,
    ClassifierExternalValidationRead,
)
from transcriptforge_api.services import external_validations as validation_service
from transcriptforge_api.storage import get_storage_backend
from transcriptforge_api.storage.base import StorageBackend, StoredObject

router = APIRouter(tags=["classifier external validation"])
Session = Annotated[AsyncSession, Depends(get_session)]
Storage = Annotated[StorageBackend, Depends(get_storage_backend)]


async def _read_upload(upload: UploadFile, artifact_name: str) -> bytes:
    payload = await upload.read(validation_service.MAX_ARTIFACT_BYTES + 1)
    if len(payload) > validation_service.MAX_ARTIFACT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"{validation_service.ARTIFACT_SPECS[artifact_name][0]} exceeds 10 MiB.",
        )
    return payload


def _safe_filename(value: str | None, fallback: str) -> str:
    candidate = Path(value or "").name
    sanitized = "".join(
        character
        for character in candidate
        if character.isascii() and (character.isalnum() or character in "._- ")
    ).strip()
    return sanitized[:200] or fallback


@router.post(
    "/projects/{project_id}/classifier-external-validations",
    response_model=ClassifierExternalValidationRead,
    status_code=status.HTTP_201_CREATED,
)
async def import_external_validation(
    project_id: str,
    session: Session,
    storage: Storage,
    metadata: Annotated[str, Form(max_length=50_000)],
    protocol: Annotated[UploadFile, File()],
    result: Annotated[UploadFile, File()],
    prediction: Annotated[UploadFile | None, File()] = None,
    model: Annotated[UploadFile | None, File()] = None,
    development_results: Annotated[UploadFile | None, File()] = None,
) -> dict[str, Any]:
    if await session.get(Project, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    try:
        request = ClassifierExternalValidationImport.model_validate_json(metadata)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid import metadata: {error.errors(include_url=False)}",
        ) from error
    normalized_name = request.name.strip()
    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Validation study name cannot be blank.",
        )

    uploads: dict[str, UploadFile] = {"protocol": protocol, "result": result}
    for name, upload in (
        ("prediction", prediction),
        ("model", model),
        ("development_results", development_results),
    ):
        if upload is not None:
            uploads[name] = upload
    payloads = {name: await _read_upload(upload, name) for name, upload in uploads.items()}
    try:
        documents = {
            name: validation_service.parse_and_validate(payload, name)
            for name, payload in payloads.items()
        }
        development_summary = request.development_summary.model_dump(mode="json")
        prediction_summary = validation_service.validate_provenance(
            documents, payloads, development_summary
        )
    except validation_service.ExternalValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error

    protocol_id = documents["protocol"]["protocol_id"]
    existing = await session.scalar(
        select(ClassifierExternalValidation).where(
            ClassifierExternalValidation.protocol_id == protocol_id
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This frozen validation protocol has already been imported.",
        )

    validation_id = new_id()
    namespace = ("projects", project_id, "classifier-external-validations", validation_id)
    stored_objects: list[StoredObject] = []
    artifact_records: dict[str, dict[str, Any]] = {}
    try:
        for name, upload in uploads.items():
            filename = _safe_filename(upload.filename, f"{name}.json")
            stored = await run_in_threadpool(
                storage.put, namespace, filename, BytesIO(payloads[name])
            )
            stored_objects.append(stored)
            artifact_records[name] = {
                "title": validation_service.ARTIFACT_SPECS[name][0],
                "filename": filename,
                "storage_uri": stored.uri,
                "mime_type": upload.content_type or "application/json",
                "size_bytes": stored.size_bytes,
                "sha256": stored.sha256,
            }
        protocol_document = documents["protocol"]
        result_document = documents["result"]
        record = ClassifierExternalValidation(
            id=validation_id,
            project_id=project_id,
            name=normalized_name,
            description=request.description,
            development_accession=protocol_document["development_cohort"]["accession"],
            external_accession=protocol_document["external_cohort"]["accession"],
            protocol_id=protocol_id,
            status=result_document["status"],
            development_summary_json=development_summary,
            prediction_summary_json=prediction_summary,
            protocol_json=protocol_document,
            result_json=result_document,
            artifacts_json=artifact_records,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
    except IntegrityError as error:
        await session.rollback()
        for stored in stored_objects:
            await run_in_threadpool(storage.delete, stored.uri)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This frozen validation protocol has already been imported.",
        ) from error
    except Exception:
        await session.rollback()
        for stored in stored_objects:
            await run_in_threadpool(storage.delete, stored.uri)
        raise
    return validation_service.to_read(record)


@router.get(
    "/projects/{project_id}/classifier-external-validations",
    response_model=list[ClassifierExternalValidationRead],
)
async def list_external_validations(
    project_id: str, session: Session
) -> list[dict[str, Any]]:
    if await session.get(Project, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    records = await validation_service.list_for_project(session, project_id)
    return [validation_service.to_read(record) for record in records]


@router.get(
    "/classifier-external-validations/{validation_id}",
    response_model=ClassifierExternalValidationRead,
)
async def get_external_validation(validation_id: str, session: Session) -> dict[str, Any]:
    record = await session.get(ClassifierExternalValidation, validation_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="External validation not found."
        )
    return validation_service.to_read(record)


@router.get(
    "/classifier-external-validations/{validation_id}/artifacts/{artifact_name}"
)
async def download_external_validation_artifact(
    validation_id: str,
    artifact_name: str,
    session: Session,
    storage: Storage,
) -> Response:
    record = await session.get(ClassifierExternalValidation, validation_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="External validation not found."
        )
    artifact = record.artifacts_json.get(artifact_name)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")
    payload = await run_in_threadpool(storage.read_bytes, artifact["storage_uri"])
    return Response(
        content=payload,
        media_type=artifact["mime_type"],
        headers={"Content-Disposition": f'attachment; filename="{artifact["filename"]}"'},
    )
