"""Question-first assay-development API routes."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api.db.session import get_session
from transcriptforge_api.models import AssayDevelopmentProject, Recommendation
from transcriptforge_api.routers.projects import require_project
from transcriptforge_api.schemas.guided_assay import (
    AssayProjectCreate,
    AssayProjectRead,
    AssayProjectUpdate,
    DecisionCreate,
    DecisionRead,
    GuidanceRecomputeResponse,
    GuidanceResultRead,
    QuestionCatalog,
    ReadinessResult,
    RecommendationDecision,
    RecommendationRead,
    RecommendationResolutionResponse,
    ScientificQuestionCreate,
    ScientificQuestionRead,
    StageDecisionCreate,
    TimelineEvent,
)
from transcriptforge_api.services import guided_assay as service

router = APIRouter(tags=["guided assay development"])
Session = Annotated[AsyncSession, Depends(get_session)]


async def require_assay_project(
    session: AsyncSession, assay_project_id: str
) -> AssayDevelopmentProject:
    item = await service.get_assay_project(session, assay_project_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assay project not found."
        )
    return item


async def require_recommendation(session: AsyncSession, recommendation_id: str) -> Recommendation:
    item = await service.get_recommendation(session, recommendation_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found."
        )
    return item


@router.get("/scientific-questions/catalog", response_model=QuestionCatalog)
async def question_catalog() -> QuestionCatalog:
    return service.get_question_catalog()


@router.post(
    "/assay-projects", response_model=AssayProjectRead, status_code=status.HTTP_201_CREATED
)
async def create_assay_project(
    request: AssayProjectCreate, session: Session
) -> AssayDevelopmentProject:
    await require_project(session, request.project_id)
    try:
        return await service.create_assay_project(session, request)
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This base project already has an assay-development workspace.",
        ) from exc


@router.get("/assay-projects", response_model=list[AssayProjectRead])
async def list_assay_projects(session: Session) -> list[AssayDevelopmentProject]:
    return await service.list_assay_projects(session)


@router.get("/assay-projects/{assay_project_id}", response_model=AssayProjectRead)
async def get_assay_project(assay_project_id: str, session: Session) -> AssayDevelopmentProject:
    return await require_assay_project(session, assay_project_id)


@router.get("/projects/{project_id}/assay-development", response_model=AssayProjectRead | None)
async def get_assay_project_for_base_project(
    project_id: str, session: Session
) -> AssayDevelopmentProject | None:
    await require_project(session, project_id)
    return await service.get_assay_project_for_base_project(session, project_id)


@router.patch("/assay-projects/{assay_project_id}", response_model=AssayProjectRead)
async def update_assay_project(
    assay_project_id: str, request: AssayProjectUpdate, session: Session
) -> AssayDevelopmentProject:
    item = await require_assay_project(session, assay_project_id)
    return await service.update_assay_project(session, item, request)


@router.get("/assay-projects/{assay_project_id}/readiness", response_model=ReadinessResult)
async def get_readiness(assay_project_id: str, session: Session) -> ReadinessResult:
    item = await require_assay_project(session, assay_project_id)
    return await service.get_readiness(session, item)


@router.post(
    "/assay-projects/{assay_project_id}/recompute-guidance",
    response_model=GuidanceRecomputeResponse,
)
async def recompute_guidance(assay_project_id: str, session: Session) -> GuidanceRecomputeResponse:
    item = await require_assay_project(session, assay_project_id)
    readiness, recommendations = await service.recompute_guidance(session, item)
    return GuidanceRecomputeResponse(
        readiness=readiness,
        recommendations=[service.recommendation_read(value) for value in recommendations],
    )


@router.get(
    "/assay-projects/{assay_project_id}/recommendations",
    response_model=list[RecommendationRead],
)
async def list_recommendations(
    assay_project_id: str,
    session: Session,
    recommendation_status: Literal["OPEN", "RESOLVED", "ALL"] = Query(default="OPEN"),
) -> list[RecommendationRead]:
    await require_assay_project(session, assay_project_id)
    items = await service.list_recommendations(session, assay_project_id)
    if recommendation_status == "OPEN":
        items = [item for item in items if item.status == "OPEN"]
    elif recommendation_status == "RESOLVED":
        items = [item for item in items if item.status != "OPEN"]
    return [service.recommendation_read(item) for item in items]


@router.post(
    "/assay-projects/{assay_project_id}/questions",
    response_model=ScientificQuestionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_question(
    assay_project_id: str, request: ScientificQuestionCreate, session: Session
) -> ScientificQuestionRead:
    item = await require_assay_project(session, assay_project_id)
    try:
        question = await service.create_question(session, item, request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return ScientificQuestionRead.model_validate(question)


@router.get(
    "/assay-projects/{assay_project_id}/questions",
    response_model=list[ScientificQuestionRead],
)
async def list_questions(assay_project_id: str, session: Session) -> list[ScientificQuestionRead]:
    await require_assay_project(session, assay_project_id)
    return [
        ScientificQuestionRead.model_validate(item)
        for item in await service.list_questions(session, assay_project_id)
    ]


async def _resolve(
    session: AsyncSession,
    recommendation: Recommendation,
    request: RecommendationDecision,
    resolution: Literal["ACCEPTED", "REJECTED", "MODIFIED"],
) -> RecommendationResolutionResponse:
    try:
        decision, replacement = await service.resolve_recommendation(
            session,
            recommendation,
            resolution,
            request.rationale,
            request.modified_action,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return RecommendationResolutionResponse(
        decision=service.decision_read(decision),
        replacement_recommendation=(
            service.recommendation_read(replacement) if replacement else None
        ),
    )


@router.post(
    "/recommendations/{recommendation_id}/accept", response_model=RecommendationResolutionResponse
)
async def accept_recommendation(
    recommendation_id: str, request: RecommendationDecision, session: Session
) -> RecommendationResolutionResponse:
    recommendation = await require_recommendation(session, recommendation_id)
    return await _resolve(session, recommendation, request, "ACCEPTED")


@router.post(
    "/recommendations/{recommendation_id}/reject", response_model=RecommendationResolutionResponse
)
async def reject_recommendation(
    recommendation_id: str, request: RecommendationDecision, session: Session
) -> RecommendationResolutionResponse:
    recommendation = await require_recommendation(session, recommendation_id)
    return await _resolve(session, recommendation, request, "REJECTED")


@router.post(
    "/recommendations/{recommendation_id}/modify", response_model=RecommendationResolutionResponse
)
async def modify_recommendation(
    recommendation_id: str, request: RecommendationDecision, session: Session
) -> RecommendationResolutionResponse:
    recommendation = await require_recommendation(session, recommendation_id)
    return await _resolve(session, recommendation, request, "MODIFIED")


@router.post(
    "/assay-projects/{assay_project_id}/stage-decisions",
    response_model=DecisionRead,
    status_code=status.HTTP_201_CREATED,
)
async def record_stage_decision(
    assay_project_id: str, request: StageDecisionCreate, session: Session
) -> DecisionRead:
    item = await require_assay_project(session, assay_project_id)
    decision = await service.record_stage_decision(session, item, request)
    return service.decision_read(decision)


@router.post(
    "/assay-projects/{assay_project_id}/decisions",
    response_model=DecisionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_decision(
    assay_project_id: str, request: DecisionCreate, session: Session
) -> DecisionRead:
    item = await require_assay_project(session, assay_project_id)
    decision = await service.create_decision(session, item, request)
    return service.decision_read(decision)


@router.get("/assay-projects/{assay_project_id}/decisions", response_model=list[DecisionRead])
async def list_decisions(assay_project_id: str, session: Session) -> list[DecisionRead]:
    await require_assay_project(session, assay_project_id)
    return [
        service.decision_read(item)
        for item in await service.list_decisions(session, assay_project_id)
    ]


@router.get(
    "/assay-projects/{assay_project_id}/guidance-results",
    response_model=list[GuidanceResultRead],
)
async def list_guidance_results(
    assay_project_id: str, session: Session
) -> list[GuidanceResultRead]:
    await require_assay_project(session, assay_project_id)
    return [
        GuidanceResultRead.model_validate(item)
        for item in await service.list_guidance_results(session, assay_project_id)
    ]


@router.get("/assay-projects/{assay_project_id}/timeline", response_model=list[TimelineEvent])
async def get_timeline(assay_project_id: str, session: Session) -> list[TimelineEvent]:
    await require_assay_project(session, assay_project_id)
    return await service.get_timeline(session, assay_project_id)
