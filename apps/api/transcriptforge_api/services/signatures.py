"""Persistence and provenance validation for candidate gene signatures."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api.models import Analysis, Artifact, GeneSignature, Run
from transcriptforge_api.models.enums import AnalysisType, RunState
from transcriptforge_api.schemas.signatures import GeneSignatureCreate
from transcriptforge_api.services.differential_expression import (
    DifferentialExpressionArtifactError,
    parse_results,
)


class SignatureInputError(ValueError):
    """Raised when a run cannot provide the requested candidate signature."""


async def create_signature(
    session: AsyncSession,
    run: Run,
    result_artifact: Artifact,
    result_payload: bytes,
    request: GeneSignatureCreate,
) -> GeneSignature:
    if run.state != RunState.SUCCEEDED.value:
        raise SignatureInputError("Only a successful run can create a signature draft.")
    if run.analysis_id is None or run.prepared_dataset_id is None:
        raise SignatureInputError(
            "The source run is not tied to a saved prepared-dataset analysis."
        )
    analysis = await session.get(Analysis, run.analysis_id)
    if analysis is None or analysis.analysis_type != AnalysisType.DIFFERENTIAL_EXPRESSION.value:
        raise SignatureInputError(
            "Candidate signatures can only be created from differential-expression runs."
        )
    try:
        rows, _ = parse_results(result_payload)
    except DifferentialExpressionArtifactError as error:
        raise SignatureInputError(str(error)) from error
    by_feature = {row.feature_id: row for row in rows}
    missing = [feature_id for feature_id in request.feature_ids if feature_id not in by_feature]
    if missing:
        preview = ", ".join(missing[:5])
        suffix = "" if len(missing) <= 5 else f" and {len(missing) - 5} more"
        raise SignatureInputError(
            f"Selected features are absent from the source result: {preview}{suffix}."
        )
    snapshots = [
        by_feature[feature_id].model_dump(mode="json") for feature_id in request.feature_ids
    ]
    selection = request.selection.model_dump(mode="json", exclude_none=True)
    selection.update(
        source_result_artifact_id=result_artifact.id,
        source_result_sha256=result_artifact.sha256,
        selected_feature_count=len(request.feature_ids),
    )
    signature = GeneSignature(
        project_id=analysis.project_id,
        prepared_dataset_id=run.prepared_dataset_id,
        source_analysis_id=analysis.id,
        source_run_id=run.id,
        name=request.name,
        description=request.description,
        status="draft",
        feature_ids=request.feature_ids,
        feature_snapshot_json=snapshots,
        selection_json=selection,
    )
    session.add(signature)
    await session.commit()
    await session.refresh(signature)
    return signature


async def get_signature(session: AsyncSession, signature_id: str) -> GeneSignature | None:
    return await session.get(GeneSignature, signature_id)


async def list_run_signatures(session: AsyncSession, run_id: str) -> list[GeneSignature]:
    result = await session.scalars(
        select(GeneSignature)
        .where(GeneSignature.source_run_id == run_id)
        .order_by(GeneSignature.created_at.desc(), GeneSignature.id.desc())
    )
    return list(result)


async def list_project_signatures(session: AsyncSession, project_id: str) -> list[GeneSignature]:
    result = await session.scalars(
        select(GeneSignature)
        .where(GeneSignature.project_id == project_id)
        .order_by(GeneSignature.created_at.desc(), GeneSignature.id.desc())
    )
    return list(result)
