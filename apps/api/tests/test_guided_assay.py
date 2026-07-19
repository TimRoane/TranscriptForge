"""API and rule-level coverage for guided assay-development scaffolding."""

from httpx import AsyncClient


async def _create_base_project(client: AsyncClient) -> dict[str, object]:
    response = await client.post(
        "/api/projects",
        json={"name": "Synthetic FFPE Development", "description": "Guided workflow test"},
    )
    assert response.status_code == 201
    return response.json()


async def test_question_catalog_is_public_and_constrained(client: AsyncClient) -> None:
    response = await client.get("/api/scientific-questions/catalog")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "1.0.0"
    routes = {item["key"]: item for item in payload["questions"]}
    assert routes["input_degradation_stability"]["experiment_type"] == (
        "INPUT_DEGRADATION_EXPLORATION"
    )
    assert routes["precision_reproducibility"]["study_type"] == ("PRECISION_REPRODUCIBILITY")


async def test_assay_project_guidance_and_human_decision_lifecycle(
    client: AsyncClient,
) -> None:
    project = await _create_base_project(client)
    created = await client.post(
        "/api/assay-projects",
        json={"project_id": project["id"], "name": "FFPE RNA assay"},
    )
    assert created.status_code == 201
    assay = created.json()
    assert assay["current_stage"] == "DEFINE"
    assert assay["readiness_status"] == "NEEDS_INFORMATION"

    duplicate = await client.post(
        "/api/assay-projects",
        json={"project_id": project["id"], "name": "Duplicate"},
    )
    assert duplicate.status_code == 409

    readiness = (await client.get(f"/api/assay-projects/{assay['id']}/readiness")).json()
    assert readiness["status"] == "NEEDS_INFORMATION"
    assert readiness["missing_items"][0]["rule_id"] == "DEFINE.REQUIRED_CONTEXT"
    assert readiness["missing_items"][0]["facts"]["missing_fields"] == [
        "biological_context",
        "proposed_output",
        "proposed_purpose",
        "specimen_type",
    ]
    assert readiness["missing_items"][0]["documentation_url"]

    updated = await client.patch(
        f"/api/assay-projects/{assay['id']}",
        json={
            "proposed_purpose": "Explore a stable synthetic research classifier endpoint.",
            "specimen_type": "simulated_ffpe_tumor",
            "biological_context": "Synthetic breast-tumor expression measurements.",
            "proposed_output": "expression_classifier_score",
            "assay_version": "development-unlocked",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["readiness_status"] == "READY_FOR_RECOMMENDED_ACTION"

    recommendations = (
        await client.get(f"/api/assay-projects/{assay['id']}/recommendations")
    ).json()
    assert len(recommendations) == 1
    recommendation = recommendations[0]
    assert recommendation["rule_id"] == "DEFINE.ADVANCE_FEASIBILITY_REVIEW"
    assert recommendation["scientist_decision_required"] is True
    assert recommendation["proposed_action"]["launch_automatically"] is False

    accepted = await client.post(
        f"/api/recommendations/{recommendation['id']}/accept",
        json={"rationale": "The proposed context is complete enough for feasibility work."},
    )
    assert accepted.status_code == 200
    assert accepted.json()["action_launched"] is False
    assert accepted.json()["decision"]["selected_option"] == "ACCEPTED"

    repeated = await client.post(
        f"/api/recommendations/{recommendation['id']}/accept",
        json={"rationale": "Duplicate resolution should be rejected."},
    )
    assert repeated.status_code == 409

    stage_decision = await client.post(
        f"/api/assay-projects/{assay['id']}/stage-decisions",
        json={
            "requested_stage": "FEASIBILITY",
            "decision": "ACCEPT",
            "rationale": "Proceed to feasibility planning with synthetic inputs.",
        },
    )
    assert stage_decision.status_code == 201
    current = (await client.get(f"/api/assay-projects/{assay['id']}")).json()
    assert current["current_stage"] == "FEASIBILITY"
    assert current["readiness_status"] == "NEEDS_INFORMATION"

    question = await client.post(
        f"/api/assay-projects/{assay['id']}/questions",
        json={
            "question_key": "input_degradation_stability",
            "formal_question": (
                "Estimate paired expression stability across ordered input levels while "
                "accounting for DV200 and sequencing run."
            ),
            "source": "USER_SELECTED",
        },
    )
    assert question.status_code == 201
    assert question.json()["stage"] == "FEASIBILITY"

    blocked = (await client.get(f"/api/assay-projects/{assay['id']}/readiness")).json()
    assert blocked["status"] == "BLOCKED"
    assert blocked["blockers"][0]["rule_id"] == "INPUTS.EXPRESSION_BUNDLE_REQUIRED"

    open_recommendations = (
        await client.get(f"/api/assay-projects/{assay['id']}/recommendations")
    ).json()
    bundle_action = next(
        item
        for item in open_recommendations
        if item["rule_id"] == "INPUTS.EXPRESSION_BUNDLE_REQUIRED"
    )
    assert bundle_action["requirement_level"] == "BLOCKER"
    assert bundle_action["evidence_refs"][0]["type"] == "question_catalog"

    timeline = (await client.get(f"/api/assay-projects/{assay['id']}/timeline")).json()
    event_types = {item["event_type"] for item in timeline}
    assert {
        "ASSAY_PROJECT_CREATED",
        "QUESTION_CREATED",
        "READINESS_RECOMPUTED",
        "RECOMMENDATION_CREATED",
        "RECOMMENDATION_ACCEPTED",
        "STAGE_DECISION_RECORDED",
    } <= event_types


async def test_modify_recommendation_requires_replacement_and_never_launches(
    client: AsyncClient,
) -> None:
    project = await _create_base_project(client)
    response = await client.post(
        "/api/assay-projects",
        json={"project_id": project["id"], "name": "Draft assay"},
    )
    assay_id = response.json()["id"]
    recommendation = (await client.get(f"/api/assay-projects/{assay_id}/recommendations")).json()[0]

    missing_action = await client.post(
        f"/api/recommendations/{recommendation['id']}/modify",
        json={"rationale": "Use a narrower metadata action."},
    )
    assert missing_action.status_code == 409

    modified = await client.post(
        f"/api/recommendations/{recommendation['id']}/modify",
        json={
            "rationale": "Collect specimen type before the remaining context.",
            "modified_action": {
                "action_type": "EDIT_ASSAY_PROJECT",
                "fields": ["specimen_type"],
            },
        },
    )
    assert modified.status_code == 200
    payload = modified.json()
    assert payload["action_launched"] is False
    assert payload["replacement_recommendation"]["status"] == "OPEN"
    assert payload["replacement_recommendation"]["proposed_action"]["launch_automatically"] is False
