"""Project, dataset, and file-upload API integration tests."""

import hashlib
from pathlib import Path

from httpx import AsyncClient
from transcriptforge_api.storage.local import LocalStorage


async def create_project(client: AsyncClient, name: str = "Airway study") -> dict[str, object]:
    response = await client.post(
        "/api/projects", json={"name": name, "description": "Dexamethasone experiment"}
    )
    assert response.status_code == 201
    return response.json()


async def create_dataset(client: AsyncClient, project_id: str) -> dict[str, object]:
    response = await client.post(
        f"/api/projects/{project_id}/datasets",
        json={
            "name": "Airway counts",
            "modality": "bulk_rnaseq",
            "source_kind": "count_matrix",
            "annotation_release": "GENCODE 49",
        },
    )
    assert response.status_code == 201
    return response.json()


async def test_project_crud(client: AsyncClient) -> None:
    project = await create_project(client)
    project_id = str(project["id"])
    assert project["owner_id"] == "local-user"

    listed = await client.get("/api/projects")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [project_id]

    updated = await client.patch(
        f"/api/projects/{project_id}", json={"name": "Updated airway study"}
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated airway study"

    empty_update = await client.patch(f"/api/projects/{project_id}", json={})
    assert empty_update.status_code == 422

    deleted = await client.delete(f"/api/projects/{project_id}")
    assert deleted.status_code == 204
    assert (await client.get(f"/api/projects/{project_id}")).status_code == 404


async def test_dataset_guardrails_and_project_cascade(client: AsyncClient) -> None:
    project = await create_project(client)
    project_id = str(project["id"])

    invalid = await client.post(
        f"/api/projects/{project_id}/datasets",
        json={
            "name": "Invalid pairing",
            "modality": "microarray",
            "source_kind": "fastq",
        },
    )
    assert invalid.status_code == 422
    assert "not supported" in invalid.text

    dataset = await create_dataset(client, project_id)
    dataset_id = str(dataset["id"])
    assert dataset["status"] == "draft"
    assert dataset["organism"] == "Homo sapiens"
    assert dataset["genome_build"] == "GRCh38"

    listed = await client.get(f"/api/projects/{project_id}/datasets")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [dataset_id]

    assert (await client.delete(f"/api/projects/{project_id}")).status_code == 204
    assert (await client.get(f"/api/datasets/{dataset_id}")).status_code == 404


async def test_dataset_upload_is_hashed_and_namespaced(
    client: AsyncClient, storage: LocalStorage
) -> None:
    project = await create_project(client)
    dataset = await create_dataset(client, str(project["id"]))
    dataset_id = str(dataset["id"])
    content = b"gene_id\tsample_1\nENSG000001\t42\n"

    response = await client.post(
        f"/api/datasets/{dataset_id}/files",
        data={"role": "count_matrix"},
        files={"file": ("../../counts.tsv", content, "text/tab-separated-values")},
    )

    assert response.status_code == 201
    uploaded = response.json()
    assert uploaded["original_name"] == "../../counts.tsv"
    assert uploaded["size_bytes"] == len(content)
    assert uploaded["sha256"] == hashlib.sha256(content).hexdigest()
    assert "counts" not in uploaded["storage_uri"]
    stored_path = Path(storage.path_for(uploaded["storage_uri"]))
    assert stored_path.read_bytes() == content
    assert stored_path.is_relative_to(storage.root)
