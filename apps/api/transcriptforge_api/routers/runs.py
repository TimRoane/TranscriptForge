"""Durable run status and artifact routes."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from transcriptforge_api.config import Settings, get_settings
from transcriptforge_api.db.session import get_session
from transcriptforge_api.models import Artifact, Run
from transcriptforge_api.schemas.runs import (
    ArtifactRead,
    DifferentialExpressionFeatureDetail,
    DifferentialExpressionResultsPage,
    DifferentialExpressionSort,
    RunRead,
    SortDirection,
)
from transcriptforge_api.services import differential_expression as differential_expression_service
from transcriptforge_api.services import runs as run_service
from transcriptforge_api.storage import get_storage_backend
from transcriptforge_api.storage.base import StorageBackend

router = APIRouter(tags=["runs"])
Session = Annotated[AsyncSession, Depends(get_session)]
Storage = Annotated[StorageBackend, Depends(get_storage_backend)]
Configuration = Annotated[Settings, Depends(get_settings)]


async def require_run(session: AsyncSession, run_id: str) -> Run:
    run = await run_service.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    return run


async def require_artifact(session: AsyncSession, artifact_id: str) -> Artifact:
    artifact = await run_service.get_artifact(session, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")
    return artifact


@router.get("/runs/{run_id}", response_model=RunRead)
async def get_run(run_id: str, session: Session) -> Run:
    return await require_run(session, run_id)


@router.post(
    "/runs/{run_id}/cancel",
    response_model=RunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_run(
    run_id: str,
    session: Session,
    storage: Storage,
    settings: Configuration,
) -> Run:
    run = await require_run(session, run_id)
    try:
        return await run_service.cancel_run(
            session,
            storage,
            run,
            run_work_root=str(settings.run_work_root),
        )
    except run_service.RunCancellationError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("/runs/{run_id}/artifacts", response_model=list[ArtifactRead])
async def list_run_artifacts(run_id: str, session: Session) -> list[Artifact]:
    await require_run(session, run_id)
    return await run_service.list_artifacts(session, run_id)


@router.get("/runs/{run_id}/validation-report")
async def get_validation_report(run_id: str, session: Session, storage: Storage) -> dict[str, Any]:
    await require_run(session, run_id)
    artifact = await run_service.get_artifact_by_type(session, run_id, "validation_report")
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This run does not have a validation report yet.",
        )
    payload = await run_in_threadpool(storage.read_bytes, artifact.storage_uri)
    return dict(json.loads(payload))


@router.get("/runs/{run_id}/dataset-manifest")
async def get_dataset_manifest(run_id: str, session: Session, storage: Storage) -> dict[str, Any]:
    await require_run(session, run_id)
    artifact = await run_service.get_artifact_by_type(session, run_id, "dataset_manifest")
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This run did not produce a Dataset Manifest.",
        )
    payload = await run_in_threadpool(storage.read_bytes, artifact.storage_uri)
    return dict(json.loads(payload))


async def _json_artifact(
    session: AsyncSession,
    storage: StorageBackend,
    run_id: str,
    artifact_type: str,
) -> dict[str, Any]:
    await require_run(session, run_id)
    artifact = await run_service.get_artifact_by_type(session, run_id, artifact_type)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"This run does not have a {artifact_type.replace('_', ' ')}.",
        )
    payload = await run_in_threadpool(storage.read_bytes, artifact.storage_uri)
    return dict(json.loads(payload))


async def _artifact_payload(
    session: AsyncSession,
    storage: StorageBackend,
    run_id: str,
    artifact_type: str,
    *,
    required: bool = True,
) -> bytes | None:
    await require_run(session, run_id)
    artifact = await run_service.get_artifact_by_type(session, run_id, artifact_type)
    if artifact is None:
        if not required:
            return None
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"This run does not have a {artifact_type.replace('_', ' ')}.",
        )
    return await run_in_threadpool(storage.read_bytes, artifact.storage_uri)


@router.get("/runs/{run_id}/bundle-manifest")
async def get_bundle_manifest(run_id: str, session: Session, storage: Storage) -> dict[str, Any]:
    return await _json_artifact(session, storage, run_id, "bundle_manifest")


@router.get("/runs/{run_id}/qc-summary")
async def get_qc_summary(run_id: str, session: Session, storage: Storage) -> dict[str, Any]:
    return await _json_artifact(session, storage, run_id, "qc_summary")


@router.get("/runs/{run_id}/feature-mapping-summary")
async def get_feature_mapping_summary(
    run_id: str, session: Session, storage: Storage
) -> dict[str, Any]:
    return await _json_artifact(session, storage, run_id, "feature_mapping_summary")


@router.get("/runs/{run_id}/result-manifest")
async def get_result_manifest(run_id: str, session: Session, storage: Storage) -> dict[str, Any]:
    return await _json_artifact(session, storage, run_id, "result_manifest")


@router.get("/runs/{run_id}/deconvolution-results")
async def get_deconvolution_results(
    run_id: str, session: Session, storage: Storage
) -> dict[str, Any]:
    return await _json_artifact(session, storage, run_id, "deconvolution_results")


@router.get("/runs/{run_id}/classifier-results")
async def get_classifier_results(run_id: str, session: Session, storage: Storage) -> dict[str, Any]:
    return await _json_artifact(session, storage, run_id, "classifier_results")


@router.get("/runs/{run_id}/pca-plot")
async def get_pca_plot(run_id: str, session: Session, storage: Storage) -> dict[str, Any]:
    return await _json_artifact(session, storage, run_id, "pca_plot")


@router.get("/runs/{run_id}/variance-plot")
async def get_variance_plot(run_id: str, session: Session, storage: Storage) -> dict[str, Any]:
    return await _json_artifact(session, storage, run_id, "variance_plot")


@router.get("/runs/{run_id}/embedding-plot")
async def get_embedding_plot(run_id: str, session: Session, storage: Storage) -> dict[str, Any]:
    return await _json_artifact(session, storage, run_id, "embedding_plot")


@router.get("/runs/{run_id}/dendrogram-plot")
async def get_dendrogram_plot(run_id: str, session: Session, storage: Storage) -> dict[str, Any]:
    return await _json_artifact(session, storage, run_id, "dendrogram_plot")


@router.get("/runs/{run_id}/correlation-heatmap")
async def get_correlation_heatmap(
    run_id: str, session: Session, storage: Storage
) -> dict[str, Any]:
    return await _json_artifact(session, storage, run_id, "correlation_heatmap")


@router.get("/runs/{run_id}/volcano-plot")
async def get_volcano_plot(run_id: str, session: Session, storage: Storage) -> dict[str, Any]:
    return await _json_artifact(session, storage, run_id, "volcano_plot")


@router.get("/runs/{run_id}/ma-plot")
async def get_ma_plot(run_id: str, session: Session, storage: Storage) -> dict[str, Any]:
    return await _json_artifact(session, storage, run_id, "ma_plot")


@router.get("/runs/{run_id}/p-value-distribution")
async def get_p_value_distribution(
    run_id: str, session: Session, storage: Storage
) -> dict[str, Any]:
    return await _json_artifact(session, storage, run_id, "p_value_distribution")


@router.get("/runs/{run_id}/expression-heatmap")
async def get_expression_heatmap(run_id: str, session: Session, storage: Storage) -> dict[str, Any]:
    return await _json_artifact(session, storage, run_id, "expression_heatmap")


@router.get("/runs/{run_id}/enrichment-summary")
async def get_enrichment_summary(run_id: str, session: Session, storage: Storage) -> dict[str, Any]:
    return await _json_artifact(session, storage, run_id, "enrichment_summary")


@router.get("/runs/{run_id}/signature-scores")
async def get_signature_scores(run_id: str, session: Session, storage: Storage) -> dict[str, Any]:
    return await _json_artifact(session, storage, run_id, "signature_scores")


@router.get(
    "/runs/{run_id}/differential-expression/results",
    response_model=DifferentialExpressionResultsPage,
)
async def get_differential_expression_results(
    run_id: str,
    session: Session,
    storage: Storage,
    search: Annotated[str | None, Query(max_length=200)] = None,
    fdr_max: Annotated[float | None, Query(ge=0, le=1)] = None,
    absolute_log2_fold_change_min: Annotated[float | None, Query(ge=0)] = None,
    significant_only: bool = False,
    sort_by: DifferentialExpressionSort = "adjusted_p_value",
    direction: SortDirection = "asc",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DifferentialExpressionResultsPage:
    payload = await _artifact_payload(session, storage, run_id, "differential_expression_results")
    assert payload is not None
    try:
        return await run_in_threadpool(
            lambda: differential_expression_service.result_page(
                payload,
                search=search,
                fdr_max=fdr_max,
                absolute_log2_fold_change_min=absolute_log2_fold_change_min,
                significant_only=significant_only,
                sort_by=sort_by,
                direction=direction,
                offset=offset,
                limit=limit,
            )
        )
    except differential_expression_service.DifferentialExpressionArtifactError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("/runs/{run_id}/differential-expression/results.tsv")
async def download_filtered_differential_expression_results(
    run_id: str,
    session: Session,
    storage: Storage,
    search: Annotated[str | None, Query(max_length=200)] = None,
    fdr_max: Annotated[float | None, Query(ge=0, le=1)] = None,
    absolute_log2_fold_change_min: Annotated[float | None, Query(ge=0)] = None,
    significant_only: bool = False,
    sort_by: DifferentialExpressionSort = "adjusted_p_value",
    direction: SortDirection = "asc",
) -> Response:
    payload = await _artifact_payload(session, storage, run_id, "differential_expression_results")
    assert payload is not None
    try:
        filtered = await run_in_threadpool(
            lambda: differential_expression_service.filtered_tsv(
                payload,
                search=search,
                fdr_max=fdr_max,
                absolute_log2_fold_change_min=absolute_log2_fold_change_min,
                significant_only=significant_only,
                sort_by=sort_by,
                direction=direction,
            )
        )
    except differential_expression_service.DifferentialExpressionArtifactError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return Response(
        content=filtered,
        media_type="text/tab-separated-values",
        headers={
            "Content-Disposition": 'attachment; filename="filtered-differential-expression.tsv"'
        },
    )


@router.get(
    "/runs/{run_id}/differential-expression/features/{feature_id}",
    response_model=DifferentialExpressionFeatureDetail,
)
async def get_differential_expression_feature(
    run_id: str,
    feature_id: str,
    session: Session,
    storage: Storage,
) -> DifferentialExpressionFeatureDetail:
    result_payload = await _artifact_payload(
        session, storage, run_id, "differential_expression_results"
    )
    expression_payload = await _artifact_payload(
        session, storage, run_id, "normalized_expression", required=False
    )
    heatmap_payload = await _artifact_payload(
        session, storage, run_id, "expression_heatmap", required=False
    )
    assert result_payload is not None
    heatmap_contract = dict(json.loads(heatmap_payload)) if heatmap_payload is not None else None
    try:
        detail = await run_in_threadpool(
            differential_expression_service.feature_detail,
            result_payload,
            feature_id,
            expression_payload=expression_payload,
            heatmap_contract=heatmap_contract,
        )
    except differential_expression_service.DifferentialExpressionArtifactError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This feature is not present in the differential-expression results.",
        )
    return detail


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(artifact_id: str, session: Session, storage: Storage) -> Response:
    artifact = await require_artifact(session, artifact_id)
    payload = await run_in_threadpool(storage.read_bytes, artifact.storage_uri)
    filename = artifact.relative_path.replace('"', "")
    return Response(
        content=payload,
        media_type=artifact.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
