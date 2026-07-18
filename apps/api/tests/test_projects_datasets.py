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


async def test_affymetrix_cel_ingestion_freezes_platform_and_sample_mapping(
    client: AsyncClient,
    dispatched_preparation_ids: list[str],
) -> None:
    project = await create_project(client, "Microarray study")
    created = await client.post(
        f"/api/projects/{project['id']}/datasets",
        json={
            "name": "Human Gene ST arrays",
            "modality": "microarray",
            "source_kind": "affymetrix_cel",
        },
    )
    assert created.status_code == 201
    dataset_id = str(created.json()["id"])

    async def upload(role: str, name: str, payload: bytes) -> None:
        response = await client.post(
            f"/api/datasets/{dataset_id}/files",
            data={"role": role},
            files={"file": (name, payload, "application/octet-stream")},
        )
        assert response.status_code == 201, response.text

    calvin_header = bytes((59, 1, 0, 0)) + b"HuGene-1_0-st-v1"
    await upload("cel_file", "control_1.CEL", calvin_header + b"-control")
    await upload("cel_file", "treated_1.CEL", calvin_header + b"-treated")
    await upload("cel_file", "unused.CEL", calvin_header + b"-unused")
    await upload(
        "sample_metadata",
        "samples.tsv",
        b"sample_id\tcel_file\tcondition\tbatch\n"
        b"control_1\tcontrol_1.CEL\tcontrol\tB1\n"
        b"treated_1\ttreated_1.CEL\ttreated\tB1\n",
    )

    ingested = await client.post(
        f"/api/datasets/{dataset_id}/microarray/ingest",
        json={"aggregation_method": "highest_mad"},
    )
    assert ingested.status_code == 201, ingested.text
    manifest = ingested.json()
    assert manifest["platform"]["platform_id"] == "affymetrix_hugene_1_0_st_v1"
    assert manifest["platform"]["detected_chip_type"] == "HuGene-1_0-st-v1"
    assert manifest["platform"]["cel_format"] == "calvin"
    assert manifest["platform"]["normalization"]["engine"] == "oligo"
    assert manifest["platform"]["annotation"]["confidence"] == "explicit_platform_adapter"
    assert manifest["aggregation_method"] == "highest_mad"
    assert manifest["sample_count"] == 2
    assert manifest["samples"][1]["metadata"] == {"condition": "treated", "batch": "B1"}
    assert manifest["warnings"] == [
        "1 uploaded CEL file(s) are not referenced by sample metadata."
    ]
    assert len(manifest["platform"]["definition_sha256"]) == 64

    current = await client.get(f"/api/datasets/{dataset_id}/microarray/ingestion")
    assert current.status_code == 200
    assert current.json() == manifest
    assert (await client.get(f"/api/datasets/{dataset_id}")).json()["status"] == "valid"

    platforms = await client.get("/api/microarray-platforms")
    assert platforms.status_code == 200
    platform_lookup = {item["platform_id"]: item for item in platforms.json()}
    assert platform_lookup["affymetrix_hugene_1_0_st_v1"]["aggregation"][
        "default_method"
    ] == "highest_mad"
    assert platform_lookup["affymetrix_hg_u133_plus_2"]["normalization"][
        "engine"
    ] == "affy"
    assert platform_lookup["affymetrix_hg_u133_plus_2"]["aggregation"][
        "default_method"
    ] == "median"

    prepared = await client.post(f"/api/datasets/{dataset_id}/prepare")
    assert prepared.status_code == 202, prepared.text
    assert prepared.json()["run_type"] == "dataset_preparation"
    assert dispatched_preparation_ids == [prepared.json()["id"]]

    await upload("cel_file", "new_array.CEL", calvin_header + b"-new")
    stale = await client.get(f"/api/datasets/{dataset_id}/microarray/ingestion")
    assert stale.status_code == 200
    assert stale.json() is None
    assert (await client.get(f"/api/datasets/{dataset_id}")).json()["status"] == "draft"


async def test_affymetrix_cel_ingestion_rejects_unsupported_arrays_and_bad_mapping(
    client: AsyncClient,
) -> None:
    project = await create_project(client, "Unsupported array study")
    created = await client.post(
        f"/api/projects/{project['id']}/datasets",
        json={
            "name": "Unsupported CEL",
            "modality": "microarray",
            "source_kind": "affymetrix_cel",
        },
    )
    dataset_id = str(created.json()["id"])

    async def upload(role: str, name: str, payload: bytes) -> None:
        response = await client.post(
            f"/api/datasets/{dataset_id}/files",
            data={"role": role},
            files={"file": (name, payload, "application/octet-stream")},
        )
        assert response.status_code == 201

    await upload("cel_file", "array.CEL", bytes((59, 1, 0, 0)) + b"Clariom_S_Human")
    await upload(
        "sample_metadata",
        "samples.tsv",
        b"sample_id\tcel_file\narray\tmissing.CEL\n",
    )
    missing = await client.post(f"/api/datasets/{dataset_id}/microarray/ingest", json={})
    assert missing.status_code == 422
    assert "was not uploaded" in missing.json()["detail"]

    await upload(
        "sample_metadata",
        "samples.tsv",
        b"sample_id\tcel_file\narray\tarray.CEL\n",
    )
    unsupported = await client.post(
        f"/api/datasets/{dataset_id}/microarray/ingest", json={}
    )
    assert unsupported.status_code == 422
    assert "Unsupported array" in unsupported.json()["detail"]
    assert "HuGene-1_0-st-v1" in unsupported.json()["detail"]

    unknown_adapter = await client.post(
        f"/api/datasets/{dataset_id}/microarray/ingest",
        json={"platform_id": "unknown_affymetrix_array"},
    )
    assert unknown_adapter.status_code == 422
    assert "Supported platforms" in unknown_adapter.json()["detail"]


async def test_gpl570_ingestion_freezes_xda_affy_rma_adapter(client: AsyncClient) -> None:
    project = await create_project(client, "GPL570 classifier cohorts")
    created = await client.post(
        f"/api/projects/{project['id']}/datasets",
        json={
            "name": "HG-U133 Plus 2 arrays",
            "modality": "microarray",
            "source_kind": "affymetrix_cel",
        },
    )
    dataset_id = str(created.json()["id"])
    xda_header = (64).to_bytes(4, byteorder="little") + b"HG-U133_Plus_2"
    for role, name, payload in (
        ("cel_file", "GSM1.CEL", xda_header + b"-fixture"),
        (
            "sample_metadata",
            "samples.tsv",
            b"sample_id\tcel_file\tcohort\nGSM1\tGSM1.CEL\tdevelopment\n",
        ),
    ):
        response = await client.post(
            f"/api/datasets/{dataset_id}/files",
            data={"role": role},
            files={"file": (name, payload, "application/octet-stream")},
        )
        assert response.status_code == 201

    ingested = await client.post(
        f"/api/datasets/{dataset_id}/microarray/ingest",
        json={
            "platform_id": "affymetrix_hg_u133_plus_2",
            "aggregation_method": "median",
        },
    )

    assert ingested.status_code == 201, ingested.text
    platform = ingested.json()["platform"]
    assert platform["detected_chip_type"] == "HG-U133_Plus_2"
    assert platform["cel_format"] == "xda"
    assert platform["normalization"] == {
        "engine": "affy",
        "method": "rma",
        "target": "probeset",
        "feature_identifier": "normalized_feature_id",
        "cdf_package": "hgu133plus2cdf",
    }
    assert platform["annotation"]["package"] == "hgu133plus2.db"


async def test_raw_rnaseq_sample_sheet_ingestion_supports_paired_and_single_end(
    client: AsyncClient,
) -> None:
    project = await create_project(client, "Tiny FASTQ study")
    project_id = str(project["id"])

    async def create_fastq_dataset(name: str) -> dict[str, object]:
        response = await client.post(
            f"/api/projects/{project_id}/datasets",
            json={
                "name": name,
                "modality": "bulk_rnaseq",
                "source_kind": "fastq",
                "annotation_release": "GENCODE 50",
            },
        )
        assert response.status_code == 201
        return response.json()

    async def upload(dataset_id: str, role: str, name: str, content: bytes) -> None:
        response = await client.post(
            f"/api/datasets/{dataset_id}/files",
            data={"role": role},
            files={"file": (name, content, "application/octet-stream")},
        )
        assert response.status_code == 201, response.text

    paired = await create_fastq_dataset("Paired reads")
    paired_id = str(paired["id"])
    await upload(paired_id, "fastq_r1", "sample_A_R1.fastq.gz", b"paired-r1-a")
    await upload(paired_id, "fastq_r2", "sample_A_R2.fastq.gz", b"paired-r2-a")
    await upload(paired_id, "fastq_r1", "sample_A_L2_R1.fastq.gz", b"paired-r1-a-l2")
    await upload(paired_id, "fastq_r2", "sample_A_L2_R2.fastq.gz", b"paired-r2-a-l2")
    await upload(paired_id, "fastq_r1", "sample_B_R1.fastq.gz", b"paired-r1-b")
    await upload(paired_id, "fastq_r2", "sample_B_R2.fastq.gz", b"paired-r2-b")
    paired_sheet = (
        b"sample_id\tlane_id\tread1\tread2\tcondition\n"
        b"sample_A\tL001\tsample_A_R1.fastq.gz\tsample_A_R2.fastq.gz\tcontrol\n"
        b"sample_A\tL002\tsample_A_L2_R1.fastq.gz\tsample_A_L2_R2.fastq.gz\tcontrol\n"
        b"sample_B\tL001\tsample_B_R1.fastq.gz\tsample_B_R2.fastq.gz\ttreated\n"
    )
    await upload(paired_id, "sample_sheet", "samples.tsv", paired_sheet)

    incompatible = await client.post(
        f"/api/datasets/{paired_id}/files",
        data={"role": "count_matrix"},
        files={"file": ("counts.tsv", b"gene_id\tsample_A\n", "text/tab-separated-values")},
    )
    assert incompatible.status_code == 409
    assert "incompatible" in incompatible.json()["detail"]

    ingested = await client.post(
        f"/api/datasets/{paired_id}/raw-rnaseq/ingest",
        json={"strandedness": "reverse"},
    )
    assert ingested.status_code == 201, ingested.text
    paired_manifest = ingested.json()
    assert paired_manifest["library_layout"] == "paired_end"
    assert paired_manifest["strandedness"] == "reverse"
    assert paired_manifest["sample_count"] == 2
    assert paired_manifest["lane_count"] == 3
    assert paired_manifest["read_file_count"] == 6
    assert [lane["lane_id"] for lane in paired_manifest["samples"][0]["lanes"]] == [
        "L001",
        "L002",
    ]
    assert paired_manifest["samples"][0]["metadata"] == {"condition": "control"}
    assert paired_manifest["reference"]["annotation_release"] == "GENCODE 50"
    assert len(paired_manifest["reference"]["definition_sha256"]) == 64

    latest = await client.get(f"/api/datasets/{paired_id}/raw-rnaseq/ingestion")
    assert latest.status_code == 200
    assert latest.json() == paired_manifest
    files = await client.get(f"/api/datasets/{paired_id}/files")
    assert any(item["role"] == "raw_ingestion_manifest" for item in files.json())
    assert (await client.get(f"/api/datasets/{paired_id}")).json()["status"] == "valid"
    await upload(paired_id, "fastq_r1", "unassigned_R1.fastq.gz", b"new-input")
    stale = await client.get(f"/api/datasets/{paired_id}/raw-rnaseq/ingestion")
    assert stale.status_code == 200
    assert stale.json() is None
    assert (await client.get(f"/api/datasets/{paired_id}")).json()["status"] == "draft"

    single = await create_fastq_dataset("Single reads")
    single_id = str(single["id"])
    await upload(single_id, "fastq_r1", "sample_C.fastq", b"single-r1-c")
    await upload(
        single_id,
        "sample_sheet",
        "samples.tsv",
        b"sample_id\tread1\tread2\n" b"sample_C\tsample_C.fastq\t\n",
    )
    single_ingested = await client.post(
        f"/api/datasets/{single_id}/raw-rnaseq/ingest", json={}
    )
    assert single_ingested.status_code == 201
    assert single_ingested.json()["library_layout"] == "single_end"
    assert single_ingested.json()["samples"][0]["lanes"][0]["read2"] is None

    references = await client.get("/api/reference-bundles")
    assert references.status_code == 200
    assert references.json()[0]["reference_id"] == "gencode_v50_grch38_salmon_1_11_4"
    assert references.json()[0]["annotation_release"] == 50


async def test_raw_rnaseq_ingestion_rejects_mixed_layout_and_missing_reads(
    client: AsyncClient,
) -> None:
    project = await create_project(client, "Invalid FASTQ study")
    dataset = (
        await client.post(
            f"/api/projects/{project['id']}/datasets",
            json={
                "name": "Mixed reads",
                "modality": "bulk_rnaseq",
                "source_kind": "fastq",
                "annotation_release": "GENCODE 50",
            },
        )
    ).json()
    dataset_id = str(dataset["id"])
    for role, name in (
        ("fastq_r1", "sample_A_R1.fastq.gz"),
        ("fastq_r2", "sample_A_R2.fastq.gz"),
        ("fastq_r1", "sample_B_R1.fastq.gz"),
    ):
        response = await client.post(
            f"/api/datasets/{dataset_id}/files",
            data={"role": role},
            files={"file": (name, b"reads", "application/gzip")},
        )
        assert response.status_code == 201
    sheet = (
        b"sample_id\tread1\tread2\n"
        b"sample_A\tsample_A_R1.fastq.gz\tsample_A_R2.fastq.gz\n"
        b"sample_B\tsample_B_R1.fastq.gz\t\n"
    )
    assert (
        await client.post(
            f"/api/datasets/{dataset_id}/files",
            data={"role": "sample_sheet"},
            files={"file": ("samples.tsv", sheet, "text/tab-separated-values")},
        )
    ).status_code == 201
    mixed = await client.post(f"/api/datasets/{dataset_id}/raw-rnaseq/ingest", json={})
    assert mixed.status_code == 422
    assert "cannot mix" in mixed.json()["detail"]

    missing_sheet = (
        b"sample_id\tread1\tread2\n"
        b"sample_A\tmissing_R1.fastq.gz\tmissing_R2.fastq.gz\n"
    )
    assert (
        await client.post(
            f"/api/datasets/{dataset_id}/files",
            data={"role": "sample_sheet"},
            files={"file": ("samples.tsv", missing_sheet, "text/tab-separated-values")},
        )
    ).status_code == 201
    missing = await client.post(f"/api/datasets/{dataset_id}/raw-rnaseq/ingest", json={})
    assert missing.status_code == 422
    assert "was not uploaded" in missing.json()["detail"]


async def test_raw_rnaseq_preparation_queues_current_frozen_manifest(
    client: AsyncClient,
    dispatched_preparation_ids: list[str],
) -> None:
    project = await create_project(client, "Raw preparation study")
    created = await client.post(
        f"/api/projects/{project['id']}/datasets",
        json={
            "name": "Raw preparation",
            "modality": "bulk_rnaseq",
            "source_kind": "fastq",
            "annotation_release": "GENCODE 50",
        },
    )
    dataset_id = str(created.json()["id"])
    for role, name, payload in (
        ("fastq_r1", "sample_R1.fastq.gz", b"fixture-read-one"),
        ("fastq_r2", "sample_R2.fastq.gz", b"fixture-read-two"),
        (
            "sample_sheet",
            "samples.tsv",
            b"sample_id\tread1\tread2\n"
            b"sample\tsample_R1.fastq.gz\tsample_R2.fastq.gz\n",
        ),
    ):
        uploaded = await client.post(
            f"/api/datasets/{dataset_id}/files",
            data={"role": role},
            files={"file": (name, payload, "application/octet-stream")},
        )
        assert uploaded.status_code == 201
    ingested = await client.post(f"/api/datasets/{dataset_id}/raw-rnaseq/ingest", json={})
    assert ingested.status_code == 201

    prepared = await client.post(f"/api/datasets/{dataset_id}/prepare")
    assert prepared.status_code == 202, prepared.text
    assert prepared.json()["run_type"] == "dataset_preparation"
    assert prepared.json()["state"] == "QUEUED"
    assert dispatched_preparation_ids == [prepared.json()["id"]]
    assert (await client.get(f"/api/datasets/{dataset_id}")).json()["status"] == "preparing"
