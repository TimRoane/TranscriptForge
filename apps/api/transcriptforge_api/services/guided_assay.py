"""Persistence and deterministic guidance for assay-development projects."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api.models import (
    Analysis,
    AssayAuditEvent,
    AssayDevelopmentProject,
    Dataset,
    DecisionRecord,
    GuidanceResult,
    ModelRecord,
    PreparedDataset,
    Recommendation,
    ScientificQuestion,
)
from transcriptforge_api.models.base import utc_now
from transcriptforge_api.models.enums import (
    AssayLifecycleStage,
    AssayReadinessStatus,
    RecommendationRequirement,
)
from transcriptforge_api.schemas.guided_assay import (
    AssayProjectCreate,
    AssayProjectUpdate,
    DecisionCreate,
    DecisionRead,
    QuestionCatalog,
    ReadinessItem,
    ReadinessResult,
    RecommendationRead,
    ScientificQuestionCreate,
    StageDecisionCreate,
    TimelineEvent,
)

CATALOG_PATH = Path(__file__).resolve().parents[1] / "resources/scientific_question_catalog.json"
OPEN_RECOMMENDATION_STATUSES = {"OPEN"}


@dataclass(frozen=True)
class RecommendationDraft:
    rule_id: str
    recommendation_type: str
    title: str
    summary: str
    why: str
    what_it_resolves: str
    priority: int
    requirement_level: RecommendationRequirement
    required_inputs: list[str]
    expected_output: str
    proposed_action: dict[str, Any]
    evidence_refs: list[dict[str, Any]]
    assumptions: list[str]
    limitations: list[str]


@lru_cache
def get_question_catalog() -> QuestionCatalog:
    """Load the packaged, versioned question catalog once per process."""
    return QuestionCatalog.model_validate_json(CATALOG_PATH.read_text(encoding="utf-8"))


def recommendation_read(item: Recommendation) -> RecommendationRead:
    return RecommendationRead(
        id=item.id,
        assay_project_id=item.assay_project_id,
        source_type=item.source_type,
        source_id=item.source_id,
        rule_id=item.rule_id,
        recommendation_type=item.recommendation_type,
        title=item.title,
        summary=item.summary,
        why=item.why,
        what_it_resolves=item.what_it_resolves,
        stage=item.stage,
        priority=item.priority,
        requirement_level=item.requirement_level,
        status=item.status,
        required_inputs=item.required_inputs_json,
        expected_output=item.expected_output,
        proposed_action=item.proposed_action_json,
        evidence_refs=item.evidence_refs_json,
        assumptions=item.assumptions_json,
        limitations=item.limitations_json,
        alternative_action_ids=item.alternative_action_ids_json,
        created_at=item.created_at,
        resolved_at=item.resolved_at,
    )


def decision_read(item: DecisionRecord) -> DecisionRead:
    return DecisionRead(
        id=item.id,
        assay_project_id=item.assay_project_id,
        source_type=item.source_type,
        source_id=item.source_id,
        stage=item.stage,
        decision_key=item.decision_key,
        decision=item.decision,
        rationale=item.rationale,
        selected_option=item.selected_option,
        alternatives=item.alternatives_json,
        evidence_refs=item.evidence_refs_json,
        made_by=item.made_by,
        made_at=item.made_at,
        supersedes_decision_id=item.supersedes_decision_id,
    )


async def add_audit_event(
    session: AsyncSession,
    assay_project: AssayDevelopmentProject,
    event_type: str,
    object_type: str,
    object_id: str,
    *,
    details: dict[str, Any] | None = None,
    revision: int | None = None,
    hashes: dict[str, str] | None = None,
) -> None:
    session.add(
        AssayAuditEvent(
            assay_project_id=assay_project.id,
            event_type=event_type,
            actor="local-user",
            object_type=object_type,
            object_id=object_id,
            revision=revision,
            hashes_json=hashes or {},
            details_json=details or {},
        )
    )


async def create_assay_project(
    session: AsyncSession, request: AssayProjectCreate
) -> AssayDevelopmentProject:
    assay_project = AssayDevelopmentProject(
        **request.model_dump(mode="json"),
        readiness_status=AssayReadinessStatus.NOT_ASSESSED,
        created_by="local-user",
    )
    session.add(assay_project)
    await session.flush()
    await add_audit_event(
        session,
        assay_project,
        "ASSAY_PROJECT_CREATED",
        "AssayDevelopmentProject",
        assay_project.id,
    )
    await recompute_guidance(session, assay_project, commit=False)
    await session.commit()
    await session.refresh(assay_project)
    return assay_project


async def list_assay_projects(session: AsyncSession) -> list[AssayDevelopmentProject]:
    result = await session.scalars(
        select(AssayDevelopmentProject).order_by(AssayDevelopmentProject.updated_at.desc())
    )
    return list(result)


async def get_assay_project(
    session: AsyncSession, assay_project_id: str
) -> AssayDevelopmentProject | None:
    return await session.get(AssayDevelopmentProject, assay_project_id)


async def get_assay_project_for_base_project(
    session: AsyncSession, project_id: str
) -> AssayDevelopmentProject | None:
    result = await session.scalars(
        select(AssayDevelopmentProject).where(AssayDevelopmentProject.project_id == project_id)
    )
    return result.first()


async def update_assay_project(
    session: AsyncSession,
    assay_project: AssayDevelopmentProject,
    request: AssayProjectUpdate,
) -> AssayDevelopmentProject:
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(assay_project, field, value)
    await recompute_guidance(session, assay_project, commit=False)
    await session.commit()
    await session.refresh(assay_project)
    return assay_project


async def create_question(
    session: AsyncSession,
    assay_project: AssayDevelopmentProject,
    request: ScientificQuestionCreate,
) -> ScientificQuestion:
    catalog = get_question_catalog()
    route = next((item for item in catalog.questions if item.key == request.question_key), None)
    if route is None:
        raise ValueError("Unsupported scientific question key.")

    open_questions = await session.scalars(
        select(ScientificQuestion).where(
            ScientificQuestion.assay_project_id == assay_project.id,
            ScientificQuestion.status == "OPEN",
        )
    )
    now = utc_now()
    for existing in open_questions:
        existing.status = "SUPERSEDED"
        existing.resolved_at = now
        existing.resolution_summary = (
            "Superseded when the scientist selected a new active question."
        )

    question = ScientificQuestion(
        assay_project_id=assay_project.id,
        question_key=route.key,
        plain_language_question=route.question,
        formal_question=request.formal_question,
        stage=route.stage,
        status="OPEN",
        source=request.source,
    )
    session.add(question)
    await session.flush()
    assay_project.active_question_id = question.id
    await add_audit_event(
        session,
        assay_project,
        "QUESTION_CREATED",
        "ScientificQuestion",
        question.id,
        details={"question_key": question.question_key, "stage": question.stage},
    )
    await recompute_guidance(session, assay_project, commit=False)
    await session.commit()
    await session.refresh(question)
    return question


async def list_questions(session: AsyncSession, assay_project_id: str) -> list[ScientificQuestion]:
    result = await session.scalars(
        select(ScientificQuestion)
        .where(ScientificQuestion.assay_project_id == assay_project_id)
        .order_by(ScientificQuestion.created_at.desc())
    )
    return list(result)


async def list_guidance_results(
    session: AsyncSession, assay_project_id: str
) -> list[GuidanceResult]:
    result = await session.scalars(
        select(GuidanceResult)
        .where(GuidanceResult.assay_project_id == assay_project_id)
        .order_by(GuidanceResult.created_at.desc())
    )
    return list(result)


async def _prepared_dataset_count(
    session: AsyncSession, assay_project: AssayDevelopmentProject
) -> int:
    value = await session.scalar(
        select(func.count(PreparedDataset.id))
        .join(Dataset, PreparedDataset.dataset_id == Dataset.id)
        .where(Dataset.project_id == assay_project.project_id)
    )
    return int(value or 0)


def _item(
    rule_id: str,
    facts: dict[str, Any],
    conclusion: str,
    severity: Literal["INFO", "WARNING", "BLOCKER"],
    suggested_action: str,
    assumptions: list[str] | None = None,
) -> ReadinessItem:
    return ReadinessItem(
        rule_id=rule_id,
        facts=facts,
        conclusion=conclusion,
        severity=severity,
        suggested_action=suggested_action,
        assumptions=assumptions or [],
        documentation_url=f"/docs/guided-assay-development#{rule_id.lower().replace('.', '-')}",
    )


async def _evaluate(
    session: AsyncSession, assay_project: AssayDevelopmentProject
) -> tuple[ReadinessResult, list[RecommendationDraft]]:
    ready: list[ReadinessItem] = []
    missing: list[ReadinessItem] = []
    blockers: list[ReadinessItem] = []
    warnings: list[ReadinessItem] = []
    drafts: list[RecommendationDraft] = []
    context = {
        "proposed_purpose": assay_project.proposed_purpose,
        "specimen_type": assay_project.specimen_type,
        "biological_context": assay_project.biological_context,
        "proposed_output": assay_project.proposed_output,
    }
    absent = sorted(key for key, value in context.items() if not value)
    if absent:
        target = (
            blockers
            if "specimen_type" in absent and assay_project.current_stage != "DEFINE"
            else missing
        )
        target.append(
            _item(
                "DEFINE.REQUIRED_CONTEXT",
                {"missing_fields": absent},
                "The proposed assay context is incomplete.",
                "BLOCKER" if target is blockers else "WARNING",
                "Complete the missing assay-context fields.",
            )
        )
        drafts.append(
            RecommendationDraft(
                rule_id="DEFINE.REQUIRED_CONTEXT",
                recommendation_type="COMPLETE_PROJECT_CONTEXT",
                title="Complete the proposed assay context",
                summary=f"Record {', '.join(absent)} before planning the next stage.",
                why=(
                    "Specimen, purpose, biological context, and proposed output define "
                    "what the evidence can address."
                ),
                what_it_resolves="Missing DEFINE-stage context.",
                priority=100,
                requirement_level=RecommendationRequirement.BLOCKER
                if target is blockers
                else RecommendationRequirement.STRONGLY_RECOMMENDED,
                required_inputs=absent,
                expected_output="A recomputed stage-readiness result.",
                proposed_action={
                    "action_type": "EDIT_ASSAY_PROJECT",
                    "launch_automatically": False,
                },
                evidence_refs=[
                    {
                        "type": "assay_project",
                        "id": assay_project.id,
                        "facts": {"missing_fields": absent},
                    }
                ],
                assumptions=[],
                limitations=[
                    "TranscriptForge cannot determine the scientific appropriateness "
                    "of the proposed purpose."
                ],
            )
        )
    else:
        ready.append(
            _item(
                "DEFINE.REQUIRED_CONTEXT",
                {"complete_fields": sorted(context)},
                "The proposed purpose, specimen, biological context, and output are recorded.",
                "INFO",
                "Review the context whenever the proposed assay changes.",
            )
        )

    active_question = None
    if assay_project.active_question_id:
        active_question = await session.get(ScientificQuestion, assay_project.active_question_id)

    if not absent and assay_project.current_stage == AssayLifecycleStage.DEFINE:
        drafts.append(
            RecommendationDraft(
                rule_id="DEFINE.ADVANCE_FEASIBILITY_REVIEW",
                recommendation_type="STAGE_DECISION",
                title="Review advancement to feasibility",
                summary=(
                    "The DEFINE context is complete enough for the scientist to consider "
                    "feasibility planning."
                ),
                why="All required project-context fields are present.",
                what_it_resolves="The next lifecycle-stage decision.",
                priority=80,
                requirement_level=RecommendationRequirement.RECOMMENDED,
                required_inputs=[],
                expected_output="An accepted, rejected, or deferred stage DecisionRecord.",
                proposed_action={
                    "action_type": "REVIEW_STAGE_CHANGE",
                    "requested_stage": "FEASIBILITY",
                    "launch_automatically": False,
                },
                evidence_refs=[{"type": "readiness_rule", "id": "DEFINE.REQUIRED_CONTEXT"}],
                assumptions=["The scientist agrees the proposed context is sufficiently defined."],
                limitations=["This recommendation does not assess clinical appropriateness."],
            )
        )
    elif not absent and active_question is None:
        missing.append(
            _item(
                "GUIDANCE.ACTIVE_QUESTION_REQUIRED",
                {"active_question_id": None, "stage": assay_project.current_stage},
                "No active scientific question has been selected.",
                "WARNING",
                "Select a supported question from the catalog.",
            )
        )
        drafts.append(
            RecommendationDraft(
                rule_id="GUIDANCE.ACTIVE_QUESTION_REQUIRED",
                recommendation_type="SELECT_QUESTION",
                title="Select the next scientific question",
                summary="Begin with what the experiment or analysis needs to teach you.",
                why=(
                    "A declared question is required before TranscriptForge can route "
                    "to a constrained design."
                ),
                what_it_resolves="Missing question and action routing.",
                priority=90,
                requirement_level=RecommendationRequirement.STRONGLY_RECOMMENDED,
                required_inputs=["scientific_question"],
                expected_output="A versioned active ScientificQuestion and supported action route.",
                proposed_action={
                    "action_type": "OPEN_QUESTION_WIZARD",
                    "launch_automatically": False,
                },
                evidence_refs=[{"type": "assay_project", "id": assay_project.id}],
                assumptions=[],
                limitations=[
                    "Only cataloged question and design families are supported in version 1."
                ],
            )
        )
    elif not absent and active_question is not None:
        route = next(
            item
            for item in get_question_catalog().questions
            if item.key == active_question.question_key
        )
        bundle_count = await _prepared_dataset_count(session, assay_project)
        locked_model = None
        if route.study_type:
            locked_model = await session.scalar(
                select(ModelRecord)
                .join(Analysis, ModelRecord.analysis_id == Analysis.id)
                .where(
                    Analysis.project_id == assay_project.project_id,
                    ModelRecord.status == "LOCKED",
                    ModelRecord.model_manifest_sha256.is_not(None),
                )
                .order_by(ModelRecord.created_at.desc())
                .limit(1)
            )
        if "expression_bundle" in route.required_inputs and bundle_count == 0:
            blockers.append(
                _item(
                    "INPUTS.EXPRESSION_BUNDLE_REQUIRED",
                    {"prepared_expression_bundle_count": bundle_count, "question_key": route.key},
                    "The selected question requires a prepared Expression Bundle.",
                    "BLOCKER",
                    "Prepare or register a compatible expression dataset.",
                )
            )
            drafts.append(
                RecommendationDraft(
                    rule_id="INPUTS.EXPRESSION_BUNDLE_REQUIRED",
                    recommendation_type="REGISTER_DATASET",
                    title="Prepare an Expression Bundle",
                    summary=(
                        "Register and prepare expression measurements before creating "
                        "the routed action."
                    ),
                    why=f"The question '{route.question}' requires expression endpoints.",
                    what_it_resolves="The missing immutable input bundle.",
                    priority=100,
                    requirement_level=RecommendationRequirement.BLOCKER,
                    required_inputs=["expression_bundle"],
                    expected_output="A prepared, checksummed Expression Bundle.",
                    proposed_action={
                        "action_type": "OPEN_DATASET_WORKSPACE",
                        "launch_automatically": False,
                    },
                    evidence_refs=[{"type": "question_catalog", "id": route.key}],
                    assumptions=["Expression measurements exist or can be collected."],
                    limitations=[
                        "Retrospective mapping cannot repair laboratory randomization or blocking."
                    ],
                )
            )
        elif route.study_type and locked_model is None:
            blockers.append(
                _item(
                    "MODEL.LOCKED_ENDPOINT_REQUIRED",
                    {"question_key": route.key, "locked_model_count": 0},
                    "The selected validation question requires a locked endpoint model.",
                    "BLOCKER",
                    "Review and lock an eligible classifier model before designing the study.",
                )
            )
            drafts.append(
                RecommendationDraft(
                    rule_id="MODEL.LOCKED_ENDPOINT_REQUIRED",
                    recommendation_type="REVIEW_MODEL_CANDIDATE",
                    title="Lock an eligible endpoint model",
                    summary="Complete model review, deterministic inference, and immutable lock.",
                    why="Post-lock validation cannot fit, tune, or silently change its endpoint.",
                    what_it_resolves="The missing frozen endpoint and ModelManifest.",
                    priority=100,
                    requirement_level=RecommendationRequirement.BLOCKER,
                    required_inputs=["reviewed_model", "model_manifest"],
                    expected_output="A checksummed LOCKED model eligible for validation.",
                    proposed_action={
                        "action_type": "REVIEW_MODEL_CANDIDATE",
                        "launch_automatically": False,
                    },
                    evidence_refs=[{"type": "scientific_question", "id": active_question.id}],
                    assumptions=[],
                    limitations=["An unlocked candidate cannot be used as a validation endpoint."],
                )
            )
        else:
            model_candidate = None
            model_lock_ready = False
            if route.key == "classifier_lock_readiness":
                model_candidate = await session.scalar(
                    select(ModelRecord)
                    .join(Analysis, ModelRecord.analysis_id == Analysis.id)
                    .where(Analysis.assay_project_id == assay_project.id)
                    .order_by(ModelRecord.created_at.desc())
                    .limit(1)
                )
                model_lock_ready = bool(
                    model_candidate is not None
                    and model_candidate.status == "REVIEWED"
                    and model_candidate.inference_test_status == "PASS"
                    and model_candidate.feature_schema_sha256
                    and model_candidate.preprocessing_sha256
                    and model_candidate.model_object_sha256
                    and model_candidate.threshold_sha256
                    and model_candidate.container_digest
                )
            latest_guidance = await session.scalar(
                select(GuidanceResult)
                .where(GuidanceResult.question_id == active_question.id)
                .order_by(GuidanceResult.created_at.desc())
                .limit(1)
            )
            ready.append(
                _item(
                    "GUIDANCE.RESULT_AVAILABLE"
                    if latest_guidance is not None
                    else "GUIDANCE.QUESTION_ROUTE_READY",
                    {
                        "question_key": route.key,
                        "prepared_expression_bundle_count": bundle_count,
                        "guidance_result_id": latest_guidance.id
                        if latest_guidance is not None
                        else None,
                    },
                    "A question-aware result is available with immutable source evidence."
                    if latest_guidance is not None
                    else "The active question maps to a supported, constrained action.",
                    "INFO",
                    "Review the findings, risks, source artifacts, and next action."
                    if latest_guidance is not None
                    else "Review the routed action and its design requirements.",
                )
            )
            action_type = (
                "REVIEW_GUIDANCE_RESULT"
                if latest_guidance is not None
                else "LOCK_MODEL"
                if route.key == "classifier_lock_readiness" and model_lock_ready
                else "REVIEW_MODEL_CANDIDATE"
                if route.key == "classifier_lock_readiness"
                else "CREATE_EXPERIMENT"
                if route.experiment_type
                else "CREATE_ANALYSIS"
                if route.analysis_type
                else "CREATE_STUDY"
                if route.study_type
                else "REVIEW_MODEL_LOCK"
            )
            template = (
                "GUIDANCE_RESULT"
                if latest_guidance is not None
                else route.experiment_type
                or route.analysis_type
                or route.study_type
                or "MODEL_LOCK_REVIEW"
            )
            drafts.append(
                RecommendationDraft(
                    rule_id=(
                        f"GUIDANCE.RESULT.{latest_guidance.id}"
                        if latest_guidance is not None
                        else f"GUIDANCE.ROUTE.{route.key.upper()}"
                    ),
                    recommendation_type=action_type,
                    title=(
                        f"Review completed evidence for: {route.question}"
                        if latest_guidance is not None
                        else f"Create the recommended action for: {route.question}"
                    ),
                    summary=(
                        "The guided summary references immutable Result Bundle artifacts and "
                        "keeps the next decision under scientist control."
                        if latest_guidance is not None
                        else f"Use the supported {template} route and review all generated "
                        "assumptions before saving."
                    ),
                    why="The declared inputs and question map to this supported action family.",
                    what_it_resolves="The active scientific question.",
                    priority=70,
                    requirement_level=RecommendationRequirement.RECOMMENDED,
                    required_inputs=route.required_inputs,
                    expected_output=(
                        "A draft configuration requiring scientist review before execution."
                    ),
                    proposed_action={
                        "action_type": action_type,
                        "template": template,
                        "question_key": route.key,
                        "guidance_result_id": latest_guidance.id
                        if latest_guidance is not None
                        else None,
                        "analysis_id": latest_guidance.analysis_id
                        if latest_guidance is not None
                        else None,
                        "model_id": (
                            model_candidate.id
                            if model_candidate is not None
                            else locked_model.id
                            if locked_model is not None
                            else None
                        ),
                        "model_lock_ready": model_lock_ready,
                        "launch_automatically": False,
                    },
                    evidence_refs=[
                        {"type": "scientific_question", "id": active_question.id},
                        {
                            "type": "guidance_result"
                            if latest_guidance is not None
                            else "question_catalog",
                            "id": latest_guidance.id if latest_guidance is not None else route.key,
                        },
                    ],
                    assumptions=[
                        "The cataloged design is appropriate for the declared scientific question."
                    ],
                    limitations=[
                        "The recommendation does not select endpoints, thresholds, or "
                        "acceptance criteria for the scientist."
                    ],
                )
            )

    status = (
        AssayReadinessStatus.BLOCKED
        if blockers
        else AssayReadinessStatus.NEEDS_INFORMATION
        if missing
        else AssayReadinessStatus.READY_FOR_RECOMMENDED_ACTION
    )
    return (
        ReadinessResult(
            stage=assay_project.current_stage,
            status=status,
            evaluated_at=utc_now(),
            ready_items=ready,
            missing_items=missing,
            blockers=blockers,
            warnings=warnings,
            recommended_action_ids=[],
            alternative_action_ids=[],
            not_recommended_action_ids=[],
        ),
        drafts,
    )


async def _sync_recommendations(
    session: AsyncSession,
    assay_project: AssayDevelopmentProject,
    drafts: list[RecommendationDraft],
) -> list[Recommendation]:
    existing = list(
        await session.scalars(
            select(Recommendation)
            .where(
                Recommendation.assay_project_id == assay_project.id,
            )
            .order_by(Recommendation.created_at.desc())
        )
    )
    by_rule: dict[str, Recommendation] = {}
    for item in existing:
        by_rule.setdefault(item.rule_id, item)
    active_rules = {draft.rule_id for draft in drafts}
    now = utc_now()
    for item in existing:
        if item.status != "OPEN":
            continue
        if item.rule_id not in active_rules:
            item.status = "SUPERSEDED"
            item.resolved_at = now

    synced: list[Recommendation] = []
    for draft in drafts:
        current = by_rule.get(draft.rule_id)
        same_evidence = current is not None and current.evidence_refs_json == draft.evidence_refs
        if current is not None and current.status != "OPEN" and same_evidence:
            continue
        created = current is None or current.status != "OPEN"
        if created:
            current = Recommendation(
                assay_project_id=assay_project.id,
                source_type="READINESS",
                source_id=assay_project.id,
                rule_id=draft.rule_id,
                status="OPEN",
                stage=assay_project.current_stage,
            )
            session.add(current)
        assert current is not None
        current.recommendation_type = draft.recommendation_type
        current.title = draft.title
        current.summary = draft.summary
        current.why = draft.why
        current.what_it_resolves = draft.what_it_resolves
        current.priority = draft.priority
        current.requirement_level = draft.requirement_level
        current.required_inputs_json = draft.required_inputs
        current.expected_output = draft.expected_output
        current.proposed_action_json = draft.proposed_action
        current.evidence_refs_json = draft.evidence_refs
        current.assumptions_json = draft.assumptions
        current.limitations_json = draft.limitations
        current.alternative_action_ids_json = []
        if created:
            await session.flush()
            await add_audit_event(
                session,
                assay_project,
                "RECOMMENDATION_CREATED",
                "Recommendation",
                current.id,
                details={"rule_id": draft.rule_id},
            )
        synced.append(current)
    await session.flush()
    return synced


async def recompute_guidance(
    session: AsyncSession,
    assay_project: AssayDevelopmentProject,
    *,
    commit: bool = True,
) -> tuple[ReadinessResult, list[Recommendation]]:
    readiness, drafts = await _evaluate(session, assay_project)
    recommendations = await _sync_recommendations(session, assay_project, drafts)
    assay_project.readiness_status = readiness.status
    readiness.recommended_action_ids = [
        item.id for item in recommendations if item.requirement_level != "NOT_RECOMMENDED"
    ]
    readiness.not_recommended_action_ids = [
        item.id for item in recommendations if item.requirement_level == "NOT_RECOMMENDED"
    ]
    await add_audit_event(
        session,
        assay_project,
        "READINESS_RECOMPUTED",
        "AssayDevelopmentProject",
        assay_project.id,
        details={
            "stage": assay_project.current_stage,
            "status": readiness.status,
            "rule_ids": sorted(
                {
                    item.rule_id
                    for item in [
                        *readiness.ready_items,
                        *readiness.missing_items,
                        *readiness.blockers,
                        *readiness.warnings,
                    ]
                }
            ),
        },
    )
    if commit:
        await session.commit()
    return readiness, recommendations


async def get_readiness(
    session: AsyncSession, assay_project: AssayDevelopmentProject
) -> ReadinessResult:
    readiness, _ = await recompute_guidance(session, assay_project)
    return readiness


async def list_recommendations(
    session: AsyncSession, assay_project_id: str
) -> list[Recommendation]:
    result = await session.scalars(
        select(Recommendation)
        .where(Recommendation.assay_project_id == assay_project_id)
        .order_by(Recommendation.priority.desc(), Recommendation.created_at.desc())
    )
    return list(result)


async def get_recommendation(
    session: AsyncSession, recommendation_id: str
) -> Recommendation | None:
    return await session.get(Recommendation, recommendation_id)


async def resolve_recommendation(
    session: AsyncSession,
    recommendation: Recommendation,
    resolution: str,
    rationale: str,
    modified_action: dict[str, Any] | None = None,
) -> tuple[DecisionRecord, Recommendation | None]:
    if recommendation.status != "OPEN":
        raise ValueError("Only an open recommendation can be resolved.")
    if resolution == "MODIFIED" and not modified_action:
        raise ValueError("A modified recommendation requires a replacement action.")
    recommendation.status = resolution
    recommendation.resolved_at = utc_now()
    decision = DecisionRecord(
        assay_project_id=recommendation.assay_project_id,
        source_type="RECOMMENDATION",
        source_id=recommendation.id,
        stage=recommendation.stage,
        decision_key=f"{resolution.lower()}_recommendation",
        decision=f"{resolution.title()} the recommendation: {recommendation.title}",
        rationale=rationale,
        selected_option=resolution,
        alternatives_json=[],
        evidence_refs_json=recommendation.evidence_refs_json,
        made_by="local-user",
    )
    session.add(decision)
    replacement = None
    if modified_action is not None:
        replacement = Recommendation(
            assay_project_id=recommendation.assay_project_id,
            source_type="RECOMMENDATION",
            source_id=recommendation.id,
            rule_id=f"USER.MODIFIED.{recommendation.id}",
            recommendation_type="USER_MODIFIED_ACTION",
            title=f"Modified action: {recommendation.title}",
            summary="Scientist-modified action derived from a deterministic recommendation.",
            why=rationale,
            what_it_resolves=recommendation.what_it_resolves,
            stage=recommendation.stage,
            priority=recommendation.priority,
            requirement_level="RECOMMENDED",
            status="OPEN",
            required_inputs_json=recommendation.required_inputs_json,
            expected_output=recommendation.expected_output,
            proposed_action_json={**modified_action, "launch_automatically": False},
            evidence_refs_json=[
                *recommendation.evidence_refs_json,
                {"type": "recommendation", "id": recommendation.id},
            ],
            assumptions_json=recommendation.assumptions_json,
            limitations_json=recommendation.limitations_json,
            alternative_action_ids_json=[],
        )
        session.add(replacement)
    assay_project = await session.get(AssayDevelopmentProject, recommendation.assay_project_id)
    if assay_project is None:  # pragma: no cover - protected by foreign key
        raise ValueError("Assay project no longer exists.")
    await session.flush()
    await add_audit_event(
        session,
        assay_project,
        f"RECOMMENDATION_{resolution}",
        "Recommendation",
        recommendation.id,
        details={
            "decision_id": decision.id,
            "replacement_id": replacement.id if replacement else None,
        },
    )
    await session.commit()
    await session.refresh(decision)
    return decision, replacement


async def create_decision(
    session: AsyncSession,
    assay_project: AssayDevelopmentProject,
    request: DecisionCreate,
) -> DecisionRecord:
    decision = DecisionRecord(
        assay_project_id=assay_project.id,
        **request.model_dump(exclude={"alternatives", "evidence_refs"}, mode="json"),
        alternatives_json=request.alternatives,
        evidence_refs_json=request.evidence_refs,
        made_by="local-user",
    )
    session.add(decision)
    await session.flush()
    await add_audit_event(
        session,
        assay_project,
        "STAGE_DECISION_RECORDED" if request.source_type == "STAGE" else "DECISION_RECORDED",
        "DecisionRecord",
        decision.id,
    )
    await session.commit()
    await session.refresh(decision)
    return decision


async def record_stage_decision(
    session: AsyncSession,
    assay_project: AssayDevelopmentProject,
    request: StageDecisionCreate,
) -> DecisionRecord:
    previous_stage = assay_project.current_stage
    if request.decision == "ACCEPT":
        assay_project.current_stage = request.requested_stage
        assay_project.active_question_id = None
        assay_project.completed_at = utc_now() if request.requested_stage == "COMPLETED" else None
    decision = DecisionRecord(
        assay_project_id=assay_project.id,
        source_type="STAGE",
        source_id=assay_project.id,
        stage=previous_stage,
        decision_key="stage_transition",
        decision=(
            f"{request.decision.title()} transition from {previous_stage} "
            f"to {request.requested_stage}."
        ),
        rationale=request.rationale,
        selected_option=request.decision,
        alternatives_json=[],
        evidence_refs_json=[],
        made_by="local-user",
    )
    session.add(decision)
    await session.flush()
    await add_audit_event(
        session,
        assay_project,
        "STAGE_DECISION_RECORDED",
        "DecisionRecord",
        decision.id,
        details={
            "previous_stage": previous_stage,
            "requested_stage": request.requested_stage,
            "decision": request.decision,
        },
    )
    await recompute_guidance(session, assay_project, commit=False)
    await session.commit()
    await session.refresh(decision)
    return decision


async def list_decisions(session: AsyncSession, assay_project_id: str) -> list[DecisionRecord]:
    result = await session.scalars(
        select(DecisionRecord)
        .where(DecisionRecord.assay_project_id == assay_project_id)
        .order_by(DecisionRecord.made_at.desc())
    )
    return list(result)


async def get_timeline(session: AsyncSession, assay_project_id: str) -> list[TimelineEvent]:
    result = await session.scalars(
        select(AssayAuditEvent)
        .where(AssayAuditEvent.assay_project_id == assay_project_id)
        .order_by(AssayAuditEvent.created_at.desc())
    )
    return [
        TimelineEvent(
            id=item.id,
            event_type=item.event_type,
            actor=item.actor,
            object_type=item.object_type,
            object_id=item.object_id,
            revision=item.revision,
            hashes=item.hashes_json,
            details=item.details_json,
            created_at=item.created_at,
        )
        for item in result
    ]
