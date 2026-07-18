"""Saved analysis configuration and execution routes."""

import tarfile
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from transcriptforge_api.config import Settings, get_settings
from transcriptforge_api.db.session import get_session
from transcriptforge_api.models import Analysis, PreparedDataset, Run
from transcriptforge_api.models.enums import RunState
from transcriptforge_api.schemas.analyses import (
    AnalysisCreate,
    AnalysisRead,
    CibersortxImportRequest,
    ClassifierDesignValidationRead,
    ClassifierPreviewRequest,
    DeconvolutionCapabilitiesRead,
    DeconvolutionComparisonRead,
    DeconvolutionRegistryRead,
    DesignOptionsRead,
    DesignValidationRead,
    DifferentialExpressionPreviewRequest,
)
from transcriptforge_api.schemas.runs import RunRead
from transcriptforge_api.services import analyses as analysis_service
from transcriptforge_api.services import classifier_design as classifier_design_service
from transcriptforge_api.services import deconvolution as deconvolution_service
from transcriptforge_api.services import runs as run_service
from transcriptforge_api.services.design_validation import design_options, validate_design
from transcriptforge_api.storage import get_storage_backend
from transcriptforge_api.storage.base import StorageBackend
from transcriptforge_api.workers.dispatch import AnalysisDispatcher, get_analysis_dispatcher

router = APIRouter(tags=["analyses"])
Session = Annotated[AsyncSession, Depends(get_session)]
Storage = Annotated[StorageBackend, Depends(get_storage_backend)]
Configuration = Annotated[Settings, Depends(get_settings)]
Dispatcher = Annotated[AnalysisDispatcher, Depends(get_analysis_dispatcher)]


async def require_prepared(session: AsyncSession, prepared_id: str) -> PreparedDataset:
    prepared = await run_service.get_prepared_dataset(session, prepared_id)
    if prepared is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prepared dataset not found."
        )
    return prepared


async def require_analysis(session: AsyncSession, analysis_id: str) -> Analysis:
    analysis = await analysis_service.get_analysis(session, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")
    return analysis


@router.post(
    "/prepared-datasets/{prepared_id}/analyses",
    response_model=AnalysisRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_analysis(
    prepared_id: str, request: AnalysisCreate, session: Session, storage: Storage
) -> Analysis:
    prepared = await require_prepared(session, prepared_id)
    try:
        return await analysis_service.create_analysis(session, storage, prepared, request)
    except (analysis_service.AnalysisInputError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("/deconvolution/methods", response_model=DeconvolutionRegistryRead)
async def get_deconvolution_methods() -> DeconvolutionRegistryRead:
    return deconvolution_service.method_registry()


@router.get(
    "/prepared-datasets/{prepared_id}/deconvolution/methods",
    response_model=DeconvolutionCapabilitiesRead,
)
async def get_prepared_deconvolution_methods(
    prepared_id: str, session: Session, storage: Storage
) -> DeconvolutionCapabilitiesRead:
    prepared = await require_prepared(session, prepared_id)
    try:
        return await run_in_threadpool(
            deconvolution_service.prepared_method_capabilities, prepared, storage
        )
    except (KeyError, ValueError, tarfile.TarError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get(
    "/prepared-datasets/{prepared_id}/deconvolution/comparison",
    response_model=DeconvolutionComparisonRead,
)
async def get_prepared_deconvolution_comparison(
    prepared_id: str, session: Session, storage: Storage
) -> DeconvolutionComparisonRead:
    await require_prepared(session, prepared_id)
    return await deconvolution_service.deconvolution_comparison(session, storage, prepared_id)


@router.post(
    "/prepared-datasets/{prepared_id}/deconvolution/cibersortx-imports",
    response_model=AnalysisRead,
    status_code=status.HTTP_201_CREATED,
)
async def import_cibersortx_result(
    prepared_id: str,
    session: Session,
    storage: Storage,
    metadata: Annotated[str, Form(min_length=2, max_length=20_000)],
    file: Annotated[UploadFile, File()],
) -> Analysis:
    prepared = await require_prepared(session, prepared_id)
    try:
        request = CibersortxImportRequest.model_validate_json(metadata)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"CIBERSORTx import metadata is invalid: {error}",
        ) from error
    source = await file.read(deconvolution_service.MAX_CIBERSORTX_RESULT_BYTES + 1)
    try:
        return await deconvolution_service.import_cibersortx_result(
            session,
            storage,
            prepared,
            request,
            source_filename=file.filename or "cibersortx_result.tsv",
            source=source,
        )
    except deconvolution_service.CibersortxImportError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.get(
    "/prepared-datasets/{prepared_id}/classifier/design-options",
    response_model=DesignOptionsRead,
)
async def get_classifier_design_options(
    prepared_id: str, session: Session, storage: Storage
) -> DesignOptionsRead:
    prepared = await require_prepared(session, prepared_id)
    try:
        return await run_in_threadpool(lambda: design_options(prepared, storage)[1])
    except (KeyError, ValueError, tarfile.TarError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post(
    "/prepared-datasets/{prepared_id}/classifier/validate-design",
    response_model=ClassifierDesignValidationRead,
)
async def preview_classifier_design(
    prepared_id: str,
    request: ClassifierPreviewRequest,
    session: Session,
    storage: Storage,
) -> ClassifierDesignValidationRead:
    prepared = await require_prepared(session, prepared_id)
    try:
        return await run_in_threadpool(
            classifier_design_service.validate_classifier_design,
            prepared,
            storage,
            request,
        )
    except (KeyError, ValueError, tarfile.TarError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get(
    "/prepared-datasets/{prepared_id}/differential-expression/design-options",
    response_model=DesignOptionsRead,
)
async def get_design_options(
    prepared_id: str, session: Session, storage: Storage
) -> DesignOptionsRead:
    prepared = await require_prepared(session, prepared_id)
    try:
        return await run_in_threadpool(lambda: design_options(prepared, storage)[1])
    except (KeyError, ValueError, tarfile.TarError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post(
    "/prepared-datasets/{prepared_id}/differential-expression/validate-design",
    response_model=DesignValidationRead,
)
async def preview_design(
    prepared_id: str,
    request: DifferentialExpressionPreviewRequest,
    session: Session,
    storage: Storage,
) -> DesignValidationRead:
    prepared = await require_prepared(session, prepared_id)
    try:
        return await run_in_threadpool(validate_design, prepared, storage, request)
    except (KeyError, ValueError, tarfile.TarError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("/prepared-datasets/{prepared_id}/analyses", response_model=list[AnalysisRead])
async def list_analyses(prepared_id: str, session: Session) -> list[Analysis]:
    await require_prepared(session, prepared_id)
    return await analysis_service.list_analyses(session, prepared_id)


@router.get("/analyses/{analysis_id}", response_model=AnalysisRead)
async def get_analysis(analysis_id: str, session: Session) -> Analysis:
    return await require_analysis(session, analysis_id)


@router.get("/analyses/{analysis_id}/runs", response_model=list[RunRead])
async def list_analysis_runs(analysis_id: str, session: Session) -> list[Run]:
    await require_analysis(session, analysis_id)
    return await analysis_service.list_analysis_runs(session, analysis_id)


@router.post(
    "/analyses/{analysis_id}/run",
    response_model=RunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_analysis(
    analysis_id: str,
    session: Session,
    storage: Storage,
    settings: Configuration,
    dispatch: Dispatcher,
) -> Run:
    analysis = await require_analysis(session, analysis_id)
    try:
        run = await analysis_service.create_analysis_run(
            session, storage, analysis, profile=settings.nextflow_profile
        )
    except analysis_service.AnalysisInputError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    try:
        await run_in_threadpool(dispatch, run.id)
    except Exception as error:
        run.state = RunState.FAILED.value
        run.error_summary = "The analysis task could not be queued."
        run.finished_at = datetime.now(UTC)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The analysis worker queue is unavailable.",
        ) from error
    return run


@router.post(
    "/analyses/{analysis_id}/clone",
    response_model=AnalysisRead,
    status_code=status.HTTP_201_CREATED,
)
async def clone_analysis(analysis_id: str, session: Session) -> Analysis:
    source = await require_analysis(session, analysis_id)
    return await analysis_service.clone_analysis(session, source)
