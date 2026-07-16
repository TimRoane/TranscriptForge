"""Dataset validation launch and durable run API tests."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from transcriptforge_api.models import Dataset, Run


async def _create_dataset(client: AsyncClient) -> str:
    project = await client.post("/api/projects", json={"name": "Validation study"})
    assert project.status_code == 201
    dataset = await client.post(
        f"/api/projects/{project.json()['id']}/datasets",
        json={
            "name": "Validation counts",
            "modality": "bulk_rnaseq",
            "source_kind": "count_matrix",
            "annotation_release": "GENCODE 49",
        },
    )
    assert dataset.status_code == 201
    return str(dataset.json()["id"])


async def _upload_inputs(client: AsyncClient, dataset_id: str) -> None:
    matrix = b"gene_id\tsample_1\nENSG000001\t42\n"
    metadata = b"sample_id\tcondition\nsample_1\tcontrol\n"
    for role, name, content in (
        ("count_matrix", "counts.tsv", matrix),
        ("sample_metadata", "metadata.tsv", metadata),
    ):
        response = await client.post(
            f"/api/datasets/{dataset_id}/files",
            data={"role": role},
            files={"file": (name, content, "text/tab-separated-values")},
        )
        assert response.status_code == 201


async def test_validation_requires_both_matrix_inputs(client: AsyncClient) -> None:
    dataset_id = await _create_dataset(client)
    response = await client.post(f"/api/datasets/{dataset_id}/validate", json={})
    assert response.status_code == 409
    assert "count_matrix" in response.json()["detail"]
    assert "sample_metadata" in response.json()["detail"]


async def test_validation_creates_queued_run_and_dispatches(
    client: AsyncClient, dispatched_run_ids: list[str]
) -> None:
    dataset_id = await _create_dataset(client)
    await _upload_inputs(client, dataset_id)

    response = await client.post(f"/api/datasets/{dataset_id}/validate", json={})

    assert response.status_code == 202
    run = response.json()
    assert run["run_type"] == "dataset_validation"
    assert run["state"] == "QUEUED"
    assert dispatched_run_ids == [run["id"]]
    dataset = await client.get(f"/api/datasets/{dataset_id}")
    assert dataset.json()["status"] == "validating"
    listed = await client.get(f"/api/datasets/{dataset_id}/validation-runs")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [run["id"]]
    assert (await client.get(f"/api/runs/{run['id']}")).status_code == 200
    report = await client.get(f"/api/runs/{run['id']}/validation-report")
    assert report.status_code == 404


async def test_validation_rejects_a_second_active_run(
    client: AsyncClient, dispatched_run_ids: list[str]
) -> None:
    dataset_id = await _create_dataset(client)
    await _upload_inputs(client, dataset_id)
    assert (await client.post(f"/api/datasets/{dataset_id}/validate", json={})).status_code == 202
    duplicate = await client.post(f"/api/datasets/{dataset_id}/validate", json={})
    assert duplicate.status_code == 409
    assert "active validation run" in duplicate.json()["detail"]
    assert len(dispatched_run_ids) == 1


async def test_validated_dataset_can_launch_immutable_preparation(
    client: AsyncClient,
    dispatched_run_ids: list[str],
    dispatched_preparation_ids: list[str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    dataset_id = await _create_dataset(client)
    await _upload_inputs(client, dataset_id)
    validation = await client.post(f"/api/datasets/{dataset_id}/validate", json={})
    assert validation.status_code == 202
    async with session_factory() as session:
        run = await session.get(Run, validation.json()["id"])
        dataset = await session.get(Dataset, dataset_id)
        assert run is not None and dataset is not None
        run.state = "SUCCEEDED"
        dataset.status = "valid"
        await session.commit()

    response = await client.post(f"/api/datasets/{dataset_id}/prepare")

    assert response.status_code == 202
    run = response.json()
    assert run["run_type"] == "dataset_preparation"
    assert run["state"] == "QUEUED"
    assert dispatched_preparation_ids == [run["id"]]
    assert dispatched_run_ids == [validation.json()["id"]]
    assert (await client.get(f"/api/datasets/{dataset_id}")).json()["status"] == "preparing"
    preparation_runs = await client.get(f"/api/datasets/{dataset_id}/preparation-runs")
    assert [item["id"] for item in preparation_runs.json()] == [run["id"]]
    prepared_versions = await client.get(f"/api/datasets/{dataset_id}/prepared-versions")
    assert prepared_versions.json() == []
