"""Pre-lock Development Experiment lifecycle and execution routes."""

import json
import tarfile
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from transcriptforge_api.config import Settings, get_settings
from transcriptforge_api.db.session import get_session
from transcriptforge_api.models import (
    Artifact,
    AssayDevelopmentProject,
    Dataset,
    ExperimentPlan,
    PreparedDataset,
    Recommendation,
    Run,
)
from transcriptforge_api.models.enums import RunState
from transcriptforge_api.schemas.experiments import (
    ExperimentCreate,
    ExperimentDesignOptions,
    ExperimentInputOption,
    ExperimentRead,
    ExperimentResultResponse,
    ExperimentRunResponse,
    ExperimentUpdate,
)
from transcriptforge_api.schemas.guided_assay import RecommendationDecision, RecommendationRead
from transcriptforge_api.services import experiments as service
from transcriptforge_api.services import guided_assay as guidance_service
from transcriptforge_api.services.design_validation import design_options
from transcriptforge_api.services.guided_assay import recommendation_read
from transcriptforge_api.storage import get_storage_backend
from transcriptforge_api.storage.base import StorageBackend
from transcriptforge_api.workers.dispatch import (
    ExperimentDispatcher,
    get_experiment_dispatcher,
)

router = APIRouter(tags=["development experiments"])
Session = Annotated[AsyncSession, Depends(get_session)]
Storage = Annotated[StorageBackend, Depends(get_storage_backend)]
Configuration = Annotated[Settings, Depends(get_settings)]
Dispatcher = Annotated[ExperimentDispatcher, Depends(get_experiment_dispatcher)]


async def require_experiment(session: AsyncSession, experiment_id: str) -> ExperimentPlan:
    item = await service.get_experiment(session, experiment_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Development Experiment not found.",
        )
    return item


@router.get(
    "/assay-projects/{assay_project_id}/experiment-input-options",
    response_model=list[ExperimentInputOption],
)
async def experiment_input_options(
    assay_project_id: str, session: Session
) -> list[ExperimentInputOption]:
    assay_project = await session.get(AssayDevelopmentProject, assay_project_id)
    if assay_project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assay project not found."
        )
    result = await session.execute(
        select(PreparedDataset, Dataset)
        .join(Dataset, PreparedDataset.dataset_id == Dataset.id)
        .where(Dataset.project_id == assay_project.project_id)
        .order_by(Dataset.name, PreparedDataset.version.desc())
    )
    return [
        ExperimentInputOption(
            prepared_dataset_id=prepared.id,
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            prepared_version=prepared.version,
            sample_count=prepared.sample_count,
            feature_count=prepared.feature_count,
            assays=list(prepared.value_types_available),
            qc_status=prepared.qc_status,
        )
        for prepared, dataset in result.all()
    ]


@router.get(
    "/prepared-datasets/{prepared_dataset_id}/experiment-design-options",
    response_model=ExperimentDesignOptions,
)
async def experiment_design_options(
    prepared_dataset_id: str, session: Session, storage: Storage
) -> ExperimentDesignOptions:
    prepared = await session.get(PreparedDataset, prepared_dataset_id)
    if prepared is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prepared Expression Bundle not found.",
        )
    try:
        rows, options = await run_in_threadpool(design_options, prepared, storage)
    except (KeyError, ValueError, tarfile.TarError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return ExperimentDesignOptions(
        prepared_dataset_id=prepared.id,
        sample_count=options.sample_count,
        assays=options.assays,
        measurement_ids=[row["sample_id"] for row in rows],
        metadata_columns=list(rows[0]),
        metadata_rows=rows,
    )


@router.post(
    "/experiments",
    response_model=ExperimentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_experiment(request: ExperimentCreate, session: Session) -> ExperimentRead:
    try:
        return service.experiment_read(await service.create_experiment(session, request))
    except service.ExperimentError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get(
    "/assay-projects/{assay_project_id}/experiments",
    response_model=list[ExperimentRead],
)
async def list_experiments(assay_project_id: str, session: Session) -> list[ExperimentRead]:
    return [
        service.experiment_read(item)
        for item in await service.list_experiments(session, assay_project_id)
    ]


@router.get("/experiments/{experiment_id}", response_model=ExperimentRead)
async def get_experiment(experiment_id: str, session: Session) -> ExperimentRead:
    return service.experiment_read(await require_experiment(session, experiment_id))


@router.patch("/experiments/{experiment_id}", response_model=ExperimentRead)
async def update_experiment(
    experiment_id: str, request: ExperimentUpdate, session: Session
) -> ExperimentRead:
    item = await require_experiment(session, experiment_id)
    try:
        return service.experiment_read(await service.update_experiment(session, item, request))
    except service.ExperimentError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/experiments/{experiment_id}/validate-design", response_model=ExperimentRead)
async def validate_design(experiment_id: str, session: Session) -> ExperimentRead:
    item = await require_experiment(session, experiment_id)
    try:
        return service.experiment_read(await service.validate_design(session, item))
    except service.ExperimentError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post(
    "/experiments/{experiment_id}/lock-execution-revision",
    response_model=ExperimentRead,
)
async def lock_execution_revision(
    experiment_id: str, session: Session, storage: Storage
) -> ExperimentRead:
    item = await require_experiment(session, experiment_id)
    try:
        return service.experiment_read(await service.lock_experiment(session, storage, item))
    except service.ExperimentError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post(
    "/experiments/{experiment_id}/run",
    response_model=ExperimentRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_experiment(
    experiment_id: str,
    session: Session,
    storage: Storage,
    settings: Configuration,
    dispatch: Dispatcher,
) -> ExperimentRunResponse:
    if not settings.assay_experiment_execution_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Development Experiment execution is disabled by configuration. "
                "The design may still be reviewed and exported."
            ),
        )
    item = await require_experiment(session, experiment_id)
    try:
        run = await service.create_experiment_run(
            session, storage, item, profile=settings.nextflow_profile
        )
    except service.ExperimentError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    try:
        await run_in_threadpool(dispatch, run.id)
    except Exception as error:
        run.state = RunState.FAILED
        run.error_summary = "The Development Experiment task could not be queued."
        run.finished_at = datetime.now(UTC)
        item.status = "FAILED"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The experiment worker queue is unavailable.",
        ) from error
    return ExperimentRunResponse(
        experiment=service.experiment_read(item),
        run_id=run.id,
        run_state="QUEUED",
    )


@router.post(
    "/experiments/{experiment_id}/clone",
    response_model=ExperimentRead,
    status_code=status.HTTP_201_CREATED,
)
async def clone_experiment(experiment_id: str, session: Session) -> ExperimentRead:
    source = await require_experiment(session, experiment_id)
    return service.experiment_read(await service.clone_experiment(session, source))


@router.get(
    "/experiments/{experiment_id}/recommendations",
    response_model=list[RecommendationRead],
)
async def experiment_recommendations(
    experiment_id: str, session: Session
) -> list[RecommendationRead]:
    await require_experiment(session, experiment_id)
    result = await session.scalars(
        select(Recommendation)
        .where(
            Recommendation.source_type == "EXPERIMENT",
            Recommendation.source_id == experiment_id,
        )
        .order_by(Recommendation.created_at.desc())
    )
    return [recommendation_read(item) for item in result]


@router.post(
    "/experiments/{experiment_id}/recommendations/{recommendation_id}/accept-follow-up",
    response_model=ExperimentRead,
    status_code=status.HTTP_201_CREATED,
)
async def accept_experiment_follow_up(
    experiment_id: str,
    recommendation_id: str,
    request: RecommendationDecision,
    session: Session,
) -> ExperimentRead:
    experiment = await require_experiment(session, experiment_id)
    recommendation = await session.get(Recommendation, recommendation_id)
    if (
        recommendation is None
        or recommendation.source_type != "EXPERIMENT"
        or recommendation.source_id != experiment.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Experiment follow-up recommendation not found.",
        )
    try:
        await guidance_service.resolve_recommendation(
            session,
            recommendation,
            "ACCEPTED",
            request.rationale,
            None,
        )
        follow_up = await service.clone_experiment(session, experiment, follow_up=True)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return service.experiment_read(follow_up)


@router.get("/experiments/{experiment_id}/results", response_model=ExperimentResultResponse)
async def experiment_results(
    experiment_id: str, session: Session, storage: Storage
) -> ExperimentResultResponse:
    experiment = await require_experiment(session, experiment_id)
    run = await session.scalar(
        select(Run)
        .where(Run.experiment_id == experiment_id)
        .order_by(Run.created_at.desc())
        .limit(1)
    )
    if run is None:
        return ExperimentResultResponse(
            experiment_id=experiment.id,
            status=experiment.status,
            run_id=None,
            decision_summary=None,
            recommendations=None,
            artifacts=[],
        )
    artifacts = list(
        await session.scalars(
            select(Artifact).where(Artifact.run_id == run.id).order_by(Artifact.display_order)
        )
    )
    by_type = {item.artifact_type: item for item in artifacts}
    decision = by_type.get("experiment_decision_summary")
    recommendations = by_type.get("experiment_recommendations")
    return ExperimentResultResponse(
        experiment_id=experiment.id,
        status=experiment.status,
        run_id=run.id,
        decision_summary=(
            json.loads(storage.read_bytes(decision.storage_uri)) if decision else None
        ),
        recommendations=(
            json.loads(storage.read_bytes(recommendations.storage_uri)) if recommendations else None
        ),
        artifacts=[
            {
                "id": item.id,
                "artifact_type": item.artifact_type,
                "title": item.title,
                "relative_path": item.relative_path,
                "mime_type": item.mime_type,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
            }
            for item in artifacts
        ],
    )


@router.get("/experiments/{experiment_id}/wet-lab-package")
async def wet_lab_package(experiment_id: str, session: Session) -> StreamingResponse:
    experiment = await require_experiment(session, experiment_id)
    paired = experiment.experiment_type == "PAIRED_CONDITION_COMPARISON"
    required_metadata = (
        "measurement_id,biological_sample_id,condition,run,operator,reagent_lot,"
        "quality_metric,processing_order\n"
        if paired
        else "measurement_id,biological_sample_id,input_ng,dv200,sequencing_run,"
        "operator,reagent_lot,instrument,processing_order\n"
    )
    schedule = (
        "measurement_id,processing_order,condition,run,operator\n"
        if paired
        else "measurement_id,processing_order,sequencing_run,operator\n"
    )
    checklist = (
        "Record condition, run, operator, lot, quality metric, and deviations.\n"
        if paired
        else "Record input, DV200, run, operator, lot, instrument, and deviations.\n"
    )
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr(
            "experiment_spec.json",
            json.dumps(experiment.experiment_spec_json, indent=2, sort_keys=True) + "\n",
        )
        package.writestr(
            "sample_assignment.tsv",
            service._assignment_tsv(experiment.assignments_json),
        )
        package.writestr(
            "required_metadata_template.csv",
            required_metadata,
        )
        package.writestr(
            "randomization_schedule.csv",
            schedule,
        )
        package.writestr(
            "plate_or_batch_layout.csv",
            "measurement_id,plate,well,batch\n",
        )
        package.writestr(
            "protocol_variable_checklist.md",
            "# Protocol variable checklist\n\n" + checklist,
        )
        package.writestr(
            "acceptance_or_learning_questions.md",
            "# Exploratory learning questions\n\n"
            + "\n".join(
                f"- {item}"
                for item in experiment.experiment_spec_json["success_guidance"][
                    "declared_questions"
                ]
            )
            + "\n",
        )
        package.writestr(
            "readme.md",
            "# Wet-lab execution package\n\n"
            "This planning export does not replace an approved laboratory protocol. "
            "Scientist review is required.\n",
        )
    archive.seek(0)
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="experiment-{experiment.id}-execution.zip"'
            )
        },
    )
