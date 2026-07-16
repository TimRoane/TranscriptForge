"""Candidate gene signature persistence and provenance tests."""

from io import BytesIO

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from transcriptforge_api.models import (
    Analysis,
    Artifact,
    Dataset,
    PreparedDataset,
    Project,
    Run,
)
from transcriptforge_api.models.base import new_id
from transcriptforge_api.storage.local import LocalStorage


async def _signature_source(
    session_factory: async_sessionmaker[AsyncSession], storage: LocalStorage
) -> tuple[str, str, str]:
    project_id = new_id()
    dataset_id = new_id()
    preparation_run_id = new_id()
    prepared_id = new_id()
    analysis_id = new_id()
    run_id = new_id()
    table = (
        b"feature_id\tgene_symbol\taverage_expression\tlog2_fold_change\tstandard_error\t"
        b"statistic\tp_value\tadjusted_p_value\tcontrast\tmethod\tsignificant\n"
        b"gene_up\tUP1\t8.2\t1.4\t0.2\t7\t1e-8\t0.0001\tstimulated versus vehicle\tlimma\tTRUE\n"
        b"gene_null\t\t6.1\t0.1\t0.3\t0.33\t0.4\t0.8\tstimulated versus vehicle\tlimma\tFALSE\n"
    )
    stored = storage.put(("tests", "signatures", run_id), "results.tsv", BytesIO(table))
    async with session_factory() as session:
        session.add(Project(id=project_id, name="Signature study", owner_id="local-user"))
        session.add(
            Dataset(
                id=dataset_id,
                project_id=project_id,
                name="Signature expression",
                modality="generic_expression",
                source_kind="normalized_matrix",
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
                params_uri="test://preparation-params",
                output_uri="test://preparation-output",
                work_uri="test://preparation-work",
            )
        )
        await session.flush()
        session.add(
            PreparedDataset(
                id=prepared_id,
                dataset_id=dataset_id,
                version=1,
                preparation_run_id=preparation_run_id,
                bundle_uri=f"test://bundle-{prepared_id}",
                bundle_manifest_uri=f"test://manifest-{prepared_id}",
                value_types_available=["log_expression"],
                sample_count=12,
                feature_count=2,
                qc_status="PASS",
            )
        )
        session.add(
            Analysis(
                id=analysis_id,
                project_id=project_id,
                prepared_dataset_id=prepared_id,
                analysis_type="differential_expression",
                name="Treatment response",
                configuration_json={"analysis_type": "differential_expression"},
            )
        )
        await session.flush()
        session.add(
            Run(
                id=run_id,
                run_type="analysis",
                dataset_id=dataset_id,
                prepared_dataset_id=prepared_id,
                analysis_id=analysis_id,
                state="SUCCEEDED",
                profile="test",
                params_uri="test://analysis-params",
                output_uri="test://analysis-output",
                work_uri="test://analysis-work",
            )
        )
        await session.flush()
        session.add(
            Artifact(
                run_id=run_id,
                artifact_type="differential_expression_results",
                title="Differential-expression results",
                relative_path="differential_expression.tsv",
                storage_uri=stored.uri,
                mime_type="text/tab-separated-values",
                size_bytes=stored.size_bytes,
                sha256=stored.sha256,
                display_order=1,
                metadata_json={},
            )
        )
        await session.commit()
    return project_id, run_id, stored.sha256


async def test_create_and_list_a_provenance_frozen_signature(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
) -> None:
    project_id, run_id, result_sha256 = await _signature_source(session_factory, storage)
    created = await client.post(
        f"/api/runs/{run_id}/signatures",
        json={
            "name": "Stimulated response candidates",
            "description": "Manually reviewed candidates",
            "feature_ids": ["gene_up", "gene_null"],
            "selection": {
                "mode": "manual",
                "fdr_max": 0.05,
                "absolute_log2_fold_change_min": 1,
                "sort_by": "adjusted_p_value",
                "direction": "asc",
            },
        },
    )
    assert created.status_code == 201
    signature = created.json()
    assert signature["status"] == "draft"
    assert signature["feature_ids"] == ["gene_up", "gene_null"]
    assert signature["feature_snapshot_json"][0]["gene_symbol"] == "UP1"
    assert signature["feature_snapshot_json"][1]["adjusted_p_value"] == 0.8
    assert signature["selection_json"]["selected_feature_count"] == 2
    assert signature["selection_json"]["source_result_sha256"] == result_sha256
    assert "not independently validated" in signature["research_use_warning"]

    by_run = await client.get(f"/api/runs/{run_id}/signatures")
    by_project = await client.get(f"/api/projects/{project_id}/signatures")
    retrieved = await client.get(f"/api/signatures/{signature['id']}")
    assert [item["id"] for item in by_run.json()] == [signature["id"]]
    assert [item["id"] for item in by_project.json()] == [signature["id"]]
    assert retrieved.json()["source_run_id"] == run_id

    missing = await client.post(
        f"/api/runs/{run_id}/signatures",
        json={"name": "Invalid", "feature_ids": ["gene_missing"]},
    )
    assert missing.status_code == 409
    assert "absent from the source result" in missing.json()["detail"]

    duplicates = await client.post(
        f"/api/runs/{run_id}/signatures",
        json={"name": "Duplicates", "feature_ids": ["gene_up", "gene_up"]},
    )
    assert duplicates.status_code == 422

    async with session_factory() as session:
        run = await session.get(Run, run_id)
        assert run is not None
        run.state = "FAILED"
        await session.commit()
    failed = await client.post(
        f"/api/runs/{run_id}/signatures",
        json={"name": "Failed source", "feature_ids": ["gene_up"]},
    )
    assert failed.status_code == 409
    assert "successful run" in failed.json()["detail"]
