"""Candidate gene signature draft routes."""

import csv
import io
import json
from io import BytesIO
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from transcriptforge_api.db.session import get_session
from transcriptforge_api.models import (
    Dataset,
    GeneSignature,
    PreparedDataset,
    Project,
    SignatureDefinition,
    SignatureMapping,
)
from transcriptforge_api.models.base import new_id
from transcriptforge_api.schemas.signatures import (
    GeneSignatureCreate,
    GeneSignatureRead,
    SignatureDefinitionRead,
    SignatureMappingRecordRead,
)
from transcriptforge_api.services import runs as run_service
from transcriptforge_api.services import signature_definitions as definition_service
from transcriptforge_api.services import signatures as signature_service
from transcriptforge_api.storage import get_storage_backend
from transcriptforge_api.storage.base import StorageBackend, StoredObject

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


@router.post(
    "/projects/{project_id}/signature-definitions",
    response_model=SignatureDefinitionRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_signature_definition(
    project_id: str,
    session: Session,
    storage: Storage,
    name: Annotated[str, Form(min_length=1, max_length=200)],
    definition_format: Annotated[Literal["gene_list", "gmt"], Form()],
    identifier_type: Annotated[Literal["ensembl_gene_id", "gene_symbol", "entrez_id"], Form()],
    file: Annotated[UploadFile, File()],
    description: Annotated[str | None, Form(max_length=5000)] = None,
) -> SignatureDefinition:
    if await session.get(Project, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    normalized_name = name.strip()
    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Signature definition name cannot be blank.",
        )
    payload = await file.read(definition_service.MAX_SOURCE_BYTES + 1)
    definition_id = new_id()
    try:
        document = definition_service.parse_definition(
            payload,
            definition_id=definition_id,
            name=normalized_name,
            description=description,
            definition_format=definition_format,
            identifier_type=identifier_type,
        )
    except definition_service.SignatureDefinitionError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    namespace = ("projects", project_id, "signature-definitions", definition_id)
    source = await run_in_threadpool(
        storage.put, namespace, file.filename or "signature.tsv", BytesIO(payload)
    )
    document["source"] = {
        "original_name": file.filename or "signature.tsv",
        "storage_uri": source.uri,
        "size_bytes": source.size_bytes,
        "sha256": source.sha256,
    }
    definition_service.validate_document(document)
    manifest_payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    manifest = await run_in_threadpool(
        storage.put, namespace, "signature-definition.json", BytesIO(manifest_payload)
    )
    record = SignatureDefinition(
        id=definition_id,
        project_id=project_id,
        name=normalized_name,
        description=description,
        definition_format=definition_format,
        identifier_type=identifier_type,
        original_name=file.filename or "signature.tsv",
        source_uri=source.uri,
        source_sha256=source.sha256,
        source_size_bytes=source.size_bytes,
        manifest_uri=manifest.uri,
        manifest_sha256=manifest.sha256,
        set_count=document["set_count"],
        requested_identifier_count=document["requested_identifier_count"],
        unique_identifier_count=document["unique_identifier_count"],
        duplicate_identifier_count=document["duplicate_identifier_count"],
        weighted=document["weighted"],
        definition_json=document,
    )
    session.add(record)
    try:
        await session.commit()
        await session.refresh(record)
    except Exception:
        await run_in_threadpool(storage.delete, source.uri)
        await run_in_threadpool(storage.delete, manifest.uri)
        raise
    return record


@router.get(
    "/projects/{project_id}/signature-definitions",
    response_model=list[SignatureDefinitionRead],
)
async def list_signature_definitions(
    project_id: str, session: Session
) -> list[SignatureDefinition]:
    if await session.get(Project, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return await definition_service.list_definitions(session, project_id)


@router.get("/signature-definitions/{definition_id}", response_model=SignatureDefinitionRead)
async def get_signature_definition(definition_id: str, session: Session) -> SignatureDefinition:
    record = await session.get(SignatureDefinition, definition_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Signature definition not found."
        )
    return record


@router.post(
    "/signature-definitions/{definition_id}/map/{prepared_id}",
    response_model=SignatureMappingRecordRead,
    status_code=status.HTTP_201_CREATED,
)
async def map_signature_definition(
    definition_id: str, prepared_id: str, session: Session, storage: Storage
) -> SignatureMapping:
    definition = await session.get(SignatureDefinition, definition_id)
    prepared = await session.get(PreparedDataset, prepared_id)
    if definition is None or prepared is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Definition or prepared dataset not found.",
        )
    dataset = await session.get(Dataset, prepared.dataset_id)
    if dataset is None or dataset.project_id != definition.project_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Definition and dataset belong to different projects.",
        )
    existing = await session.scalar(
        select(SignatureMapping).where(
            SignatureMapping.signature_definition_id == definition_id,
            SignatureMapping.prepared_dataset_id == prepared_id,
        )
    )
    if existing is not None:
        return existing
    bundle = await run_in_threadpool(storage.read_bytes, prepared.bundle_uri)
    try:
        report = definition_service.map_definition(definition, prepared, bundle)
        definition_service.validate_mapping_report(report)
    except definition_service.SignatureDefinitionError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    mapping_id = new_id()
    namespace = (
        "projects",
        definition.project_id,
        "signature-mappings",
        mapping_id,
    )
    report_payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    missing_payload = _mapping_identifiers_tsv(report, "missing_identifiers")
    ambiguous_payload = _mapping_identifiers_tsv(report, "ambiguous_identifiers")
    stored_objects: list[StoredObject] = []
    try:
        stored_objects.append(
            await run_in_threadpool(
                storage.put,
                namespace,
                "mapping-report.json",
                BytesIO(report_payload),
            )
        )
        stored_objects.append(
            await run_in_threadpool(
                storage.put,
                namespace,
                "missing-identifiers.tsv",
                BytesIO(missing_payload),
            )
        )
        stored_objects.append(
            await run_in_threadpool(
                storage.put,
                namespace,
                "ambiguous-identifiers.tsv",
                BytesIO(ambiguous_payload),
            )
        )
        record = SignatureMapping(
            id=mapping_id,
            signature_definition_id=definition_id,
            prepared_dataset_id=prepared_id,
            report_uri=stored_objects[0].uri,
            report_sha256=stored_objects[0].sha256,
            missing_uri=stored_objects[1].uri,
            missing_sha256=stored_objects[1].sha256,
            ambiguous_uri=stored_objects[2].uri,
            ambiguous_sha256=stored_objects[2].sha256,
            requested_identifier_count=report["requested_identifier_count"],
            unique_identifier_count=report["unique_identifier_count"],
            mapped_identifier_count=report["mapped_identifier_count"],
            missing_identifier_count=report["missing_identifier_count"],
            ambiguous_identifier_count=report["ambiguous_identifier_count"],
            duplicate_identifier_count=report["duplicate_identifier_count"],
            mapping_coverage=report["mapping_coverage"],
            report_json=report,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record
    except IntegrityError:
        await session.rollback()
        for stored in stored_objects:
            await run_in_threadpool(storage.delete, stored.uri)
        concurrent = await session.scalar(
            select(SignatureMapping).where(
                SignatureMapping.signature_definition_id == definition_id,
                SignatureMapping.prepared_dataset_id == prepared_id,
            )
        )
        if concurrent is not None:
            return concurrent
        raise
    except Exception:
        await session.rollback()
        for stored in stored_objects:
            await run_in_threadpool(storage.delete, stored.uri)
        raise


def _mapping_identifiers_tsv(report: dict[str, Any], field: str) -> bytes:
    output = io.StringIO(newline="")
    tabular = csv.writer(output, delimiter="\t", lineterminator="\n")
    tabular.writerow(["signature_id", "signature_name", "identifier"])
    for signature_set in report["sets"]:
        for identifier in signature_set[field]:
            tabular.writerow([signature_set["signature_id"], signature_set["name"], identifier])
    return output.getvalue().encode()


@router.get(
    "/prepared-datasets/{prepared_id}/signature-mappings",
    response_model=list[SignatureMappingRecordRead],
)
async def list_signature_mappings(prepared_id: str, session: Session) -> list[SignatureMapping]:
    if await session.get(PreparedDataset, prepared_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prepared dataset not found.",
        )
    records = await session.scalars(
        select(SignatureMapping)
        .where(SignatureMapping.prepared_dataset_id == prepared_id)
        .order_by(SignatureMapping.created_at.desc(), SignatureMapping.id.desc())
    )
    return list(records)


@router.get("/signature-mappings/{mapping_id}/{document}")
async def download_signature_mapping_document(
    mapping_id: str,
    document: Literal["report.json", "missing.tsv", "ambiguous.tsv"],
    session: Session,
    storage: Storage,
) -> Response:
    mapping = await session.get(SignatureMapping, mapping_id)
    if mapping is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signature mapping not found.",
        )
    documents = {
        "report.json": (mapping.report_uri, "application/json"),
        "missing.tsv": (mapping.missing_uri, "text/tab-separated-values"),
        "ambiguous.tsv": (mapping.ambiguous_uri, "text/tab-separated-values"),
    }
    uri, media_type = documents[document]
    payload = await run_in_threadpool(storage.read_bytes, uri)
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{document}"'},
    )
