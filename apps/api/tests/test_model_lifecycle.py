"""Scientist-controlled model review, lock, integrity, clone, and retirement coverage."""

import hashlib
import io
import json
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from transcriptforge_api.models import (
    Analysis,
    Artifact,
    AssayDevelopmentProject,
    Dataset,
    ModelRecord,
    PreparedDataset,
    Project,
    Run,
)
from transcriptforge_api.models.base import new_id
from transcriptforge_api.storage.local import LocalStorage


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


async def _candidate(
    session_factory: async_sessionmaker[AsyncSession], storage: LocalStorage
) -> str:
    project_id, dataset_id, prepared_id = new_id(), new_id(), new_id()
    preparation_run_id, analysis_id, run_id, model_id = new_id(), new_id(), new_id(), new_id()
    model = {
        "schema_version": "1.0.0",
        "model_type": "binary_elastic_net_logistic_regression",
        "analysis_id": analysis_id,
        "prepared_dataset_id": prepared_id,
        "assay": "log_expression",
        "outcome_column": "condition",
        "negative_class": "control",
        "positive_class": "case",
        "selected_feature_ids": ["G1", "G2"],
        "preprocessing": {
            "feature_filter": "top_variance_fit_on_complete_development_cohort_after_validation",
            "means": [1.0, 2.0],
            "scales": [0.5, 0.75],
        },
        "estimator": {
            "coefficients": [0.8, -0.4],
            "intercept": 0.2,
            "c": 1.0,
            "l1_ratio": 0.5,
        },
        "calibration": {"method": "none", "coefficient": None, "intercept": None},
        "decision_threshold": 0.5,
    }
    card = {
        "schema_version": "1.0.0",
        "intended_use": "Research demonstration only.",
        "prohibited_use": "No clinical use.",
        "validation": {"type": "internal_grouped_repeated_nested_cross_validation"},
    }
    result = {
        "validation": {"type": "internal_grouped_repeated_nested_cross_validation"},
        "leakage_audit": {"outer_group_overlap_count": 0, "fit_scope": "training_only"},
    }
    payloads = {
        "classifier_model": ("model.json", model),
        "classifier_model_card": ("model_card.json", card),
        "classifier_inference_schema": ("inference_schema.json", {"type": "object"}),
        "classifier_inference_example": ("inference_example.tsv", "sample_id\tG1\tG2\n"),
        "classifier_results": ("classifier_results.json", result),
    }
    stored = {}
    for artifact_type, (name, payload) in payloads.items():
        content = (
            payload.encode()
            if isinstance(payload, str)
            else json.dumps(payload, indent=2, sort_keys=True).encode() + b"\n"
        )
        stored[artifact_type] = storage.put(
            ("tests", "models", model_id), name, io.BytesIO(content)
        )
    decision_rule = {
        "operator": "gte",
        "threshold": 0.5,
        "positive_class": "case",
        "negative_class": "control",
    }
    async with session_factory() as session:
        session.add(Project(id=project_id, name="Model lifecycle", owner_id="local-user"))
        session.add(
            Dataset(
                id=dataset_id,
                project_id=project_id,
                name="Development cohort",
                modality="bulk_rnaseq",
                source_kind="count_matrix",
                organism="Homo sapiens",
                status="prepared",
            )
        )
        await session.flush()
        session.add(
            Run(
                id=preparation_run_id,
                run_type="dataset_preparation",
                dataset_id=dataset_id,
                state="SUCCEEDED",
                profile="test",
                params_uri="test://prepare",
                output_uri="test://prepare-output",
                work_uri="test://prepare-work",
            )
        )
        await session.flush()
        session.add(
            PreparedDataset(
                id=prepared_id,
                dataset_id=dataset_id,
                version=1,
                preparation_run_id=preparation_run_id,
                bundle_uri="test://bundle",
                bundle_manifest_uri="test://manifest",
                value_types_available=["log_expression"],
                sample_count=12,
                feature_count=100,
                qc_status="PASS",
            )
        )
        session.add(
            Analysis(
                id=analysis_id,
                project_id=project_id,
                prepared_dataset_id=prepared_id,
                analysis_type="classifier",
                name="Candidate classifier",
                configuration_json={"method": "elastic_net"},
            )
        )
        await session.flush()
        session.add(
            Run(
                id=run_id,
                run_type="analysis",
                prepared_dataset_id=prepared_id,
                analysis_id=analysis_id,
                state="SUCCEEDED",
                profile="test",
                params_uri="test://classifier",
                output_uri="test://classifier-output",
                work_uri="test://classifier-work",
            )
        )
        await session.flush()
        for index, (artifact_type, item) in enumerate(stored.items()):
            session.add(
                Artifact(
                    run_id=run_id,
                    artifact_type=artifact_type,
                    title=artifact_type,
                    relative_path=payloads[artifact_type][0],
                    storage_uri=item.uri,
                    mime_type="application/json",
                    size_bytes=item.size_bytes,
                    sha256=item.sha256,
                    display_order=index,
                    metadata_json={},
                )
            )
        session.add(
            ModelRecord(
                id=model_id,
                analysis_id=analysis_id,
                run_id=run_id,
                model_name="Candidate classifier",
                algorithm="elastic_net_logistic_regression",
                outcome_column="condition",
                model_uri=stored["classifier_model"].uri,
                model_card_uri=stored["classifier_model_card"].uri,
                metrics_json={"validation": "internal"},
                feature_count=2,
                status="CANDIDATE",
                feature_schema_sha256=hashlib.sha256(_canonical(["G1", "G2"])).hexdigest(),
                preprocessing_sha256=hashlib.sha256(_canonical(model["preprocessing"])).hexdigest(),
                model_object_sha256=stored["classifier_model"].sha256,
                threshold_sha256=hashlib.sha256(_canonical(decision_rule)).hexdigest(),
                training_dataset_refs_json=[{"prepared_dataset_id": prepared_id}],
                validation_dataset_refs_json=[
                    {
                        "mode": "internal_grouped_repeated_nested_cross_validation",
                        "run_id": run_id,
                    }
                ],
                container_digest="sha256:" + "a" * 64,
                inference_test_status="NOT_RUN",
            )
        )
        await session.commit()
    return model_id


async def test_model_review_lock_integrity_clone_and_retire(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
) -> None:
    model_id = await _candidate(session_factory, storage)
    initial = (await client.get(f"/api/models/{model_id}/lock-readiness")).json()
    assert initial["ready"] is False
    assert initial["checks"]["candidate_reviewed"] is False

    reviewed = await client.post(
        f"/api/models/{model_id}/review",
        json={"rationale": "Leakage, serialization, intended use, and limitations reviewed."},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "REVIEWED"
    assert reviewed.json()["inference_test_status"] == "PASS"

    locked = await client.post(
        f"/api/models/{model_id}/lock",
        json={"rationale": "Freeze this research model for independent validation."},
    )
    assert locked.status_code == 200
    assert locked.json()["status"] == "LOCKED"
    assert len(locked.json()["model_manifest_sha256"]) == 64
    locked_readiness = (await client.get(f"/api/models/{model_id}/lock-readiness")).json()
    assert locked_readiness["ready"] is True
    assert locked_readiness["checks"]["candidate_reviewed"] is True
    assert (await client.get(f"/api/models/{model_id}/manifest")).status_code == 200
    assert (await client.get(f"/api/models/{model_id}/package")).content[:2] == b"\x1f\x8b"

    integrity = await client.post(f"/api/models/{model_id}/integrity")
    assert integrity.status_code == 200
    assert integrity.json()["valid"] is True

    clone = await client.post(f"/api/models/{model_id}/clone")
    assert clone.status_code == 201
    assert clone.json()["status"] == "CANDIDATE"
    assert clone.json()["parent_model_id"] == model_id

    async with session_factory() as session:
        persisted = await session.get(ModelRecord, model_id)
        assert persisted is not None
        model_path = storage.path_for(persisted.model_uri)
    asset = Path(model_path)
    asset.write_bytes(asset.read_bytes() + b"tampered")
    changed_integrity = await client.post(f"/api/models/{model_id}/integrity")
    assert changed_integrity.json()["valid"] is False
    assert changed_integrity.json()["checks"]["model_object"] is False

    retired = await client.post(
        f"/api/models/{model_id}/retire",
        json={"rationale": "Retire after the validation program closes."},
    )
    assert retired.status_code == 200
    assert retired.json()["status"] == "RETIRED"


async def test_assay_project_lists_only_linked_model_lineage(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
) -> None:
    model_id = await _candidate(session_factory, storage)
    assay_id = new_id()
    async with session_factory() as session:
        model = await session.get(ModelRecord, model_id)
        assert model is not None
        analysis = await session.get(Analysis, model.analysis_id)
        assert analysis is not None
        session.add(
            AssayDevelopmentProject(
                id=assay_id,
                project_id=analysis.project_id,
                name="Linked assay lifecycle",
                current_stage="DEVELOP",
            )
        )
        await session.flush()
        analysis.assay_project_id = assay_id
        await session.commit()

    response = await client.get(f"/api/assay-projects/{assay_id}/models")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [model_id]
    assert (await client.get(f"/api/assay-projects/{new_id()}/models")).status_code == 404
