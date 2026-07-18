"""Uploaded reusable signature definition and mapping tests."""

import io
import json
import tarfile
from io import BytesIO

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from transcriptforge_api.models import Artifact, Dataset, PreparedDataset, Project, Run
from transcriptforge_api.models.base import new_id
from transcriptforge_api.storage.local import LocalStorage


def _bundle() -> bytes:
    files = {
        "expression_bundle/bundle_manifest.json": json.dumps(
            {
                "feature_metadata": "feature_metadata.tsv",
                "sample_metadata": "sample_metadata.tsv",
            }
        ).encode(),
        "expression_bundle/feature_metadata.tsv": (
            b"feature_id\tensembl_gene_id\tgene_symbol\tentrez_id\n"
            b"ENSG000001\tENSG000001\tTP53\t7157\n"
            b"ENSG000002\tENSG000002\tEGFR\t1956\n"
        ),
        "expression_bundle/sample_metadata.tsv": (
            b"sample_id\tcondition\tbatch\tdonor_id\tage\n"
            b"sample_1\tcontrol\tA\tdonor_1\t40\n"
            b"sample_2\ttreated\tA\tdonor_1\t41\n"
            b"sample_3\tcontrol\tB\tdonor_2\t44\n"
            b"sample_4\ttreated\tB\tdonor_2\t45\n"
        ),
    }
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, payload in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(payload))
    return output.getvalue()


async def _prepared_source(
    session_factory: async_sessionmaker[AsyncSession], storage: LocalStorage
) -> tuple[str, str]:
    project_id, dataset_id, run_id, prepared_id = (new_id() for _ in range(4))
    stored = storage.put(("tests", "signature-definitions"), "bundle.tar.gz", BytesIO(_bundle()))
    async with session_factory() as session:
        session.add(Project(id=project_id, name="Signature evaluation", owner_id="local-user"))
        session.add(
            Dataset(
                id=dataset_id,
                project_id=project_id,
                name="Expression",
                modality="microarray",
                source_kind="normalized_matrix",
                organism="Homo sapiens",
                status="prepared",
            )
        )
        await session.flush()
        session.add(
            Run(
                id=run_id,
                run_type="dataset_preparation",
                dataset_id=dataset_id,
                state="SUCCEEDED",
                profile="test",
                params_uri="test://params",
                output_uri="test://output",
                work_uri="test://work",
            )
        )
        await session.flush()
        session.add(
            PreparedDataset(
                id=prepared_id,
                dataset_id=dataset_id,
                version=1,
                preparation_run_id=run_id,
                bundle_uri=stored.uri,
                bundle_manifest_uri="test://manifest",
                value_types_available=["log_expression"],
                sample_count=4,
                feature_count=2,
                qc_status="PASS",
            )
        )
        session.add(
            Artifact(
                run_id=run_id,
                artifact_type="expression_bundle",
                title="Expression Bundle",
                relative_path="expression_bundle.tar.gz",
                storage_uri=stored.uri,
                mime_type="application/gzip",
                size_bytes=stored.size_bytes,
                sha256=stored.sha256,
                display_order=0,
                metadata_json={},
            )
        )
        await session.commit()
    return project_id, prepared_id


async def test_upload_weighted_gene_list_and_map_with_visible_coverage(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    dispatched_analysis_ids: list[str],
) -> None:
    project_id, prepared_id = await _prepared_source(session_factory, storage)
    gene_list = (
        b"gene_id\tweight\nENSG000001.9\t1.5\nENSG000002\t-0.5\n"
        b"ENSG000002\t-0.5\nENSG_MISSING\t0.25\n"
    )
    created = await client.post(
        f"/api/projects/{project_id}/signature-definitions",
        data={
            "name": "Cartilage response",
            "description": "External weighted signature",
            "definition_format": "gene_list",
            "identifier_type": "ensembl_gene_id",
        },
        files={"file": ("cartilage.tsv", gene_list, "text/tab-separated-values")},
    )
    assert created.status_code == 201, created.text
    definition = created.json()
    assert definition["weighted"] is True
    assert definition["requested_identifier_count"] == 4
    assert definition["unique_identifier_count"] == 3
    assert definition["duplicate_identifier_count"] == 1

    mapped = await client.post(f"/api/signature-definitions/{definition['id']}/map/{prepared_id}")
    assert mapped.status_code == 201, mapped.text
    mapping = mapped.json()
    report = mapping["report_json"]
    assert mapping["mapped_identifier_count"] == 2
    assert mapping["missing_identifier_count"] == 1
    assert mapping["duplicate_identifier_count"] == 1
    assert mapping["mapping_coverage"] == 2 / 3
    assert report["sets"][0]["missing_identifiers"] == ["ENSG_MISSING"]
    assert report["sets"][0]["mapped_feature_ids"] == ["ENSG000001", "ENSG000002"]
    assert report["sets"][0]["mapped_entries"] == [
        {"identifier": "ENSG000001.9", "feature_id": "ENSG000001", "weight": 1.5},
        {"identifier": "ENSG000002", "feature_id": "ENSG000002", "weight": -0.5},
    ]
    assert len(report["signature_definition_sha256"]) == 64
    assert len(report["expression_bundle_sha256"]) == 64

    repeated = await client.post(f"/api/signature-definitions/{definition['id']}/map/{prepared_id}")
    mappings = await client.get(f"/api/prepared-datasets/{prepared_id}/signature-mappings")
    report_download = await client.get(f"/api/signature-mappings/{mapping['id']}/report.json")
    missing_download = await client.get(f"/api/signature-mappings/{mapping['id']}/missing.tsv")
    ambiguous_download = await client.get(f"/api/signature-mappings/{mapping['id']}/ambiguous.tsv")
    assert repeated.json()["id"] == mapping["id"]
    assert [item["id"] for item in mappings.json()] == [mapping["id"]]
    assert report_download.json() == report
    assert missing_download.text == (
        "signature_id\tsignature_name\tidentifier\n"
        f"{definition['id']}\tCartilage response\tENSG_MISSING\n"
    )
    assert ambiguous_download.text == "signature_id\tsignature_name\tidentifier\n"

    analysis_created = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "name": "Weighted cartilage score",
            "analysis_type": "signature",
            "method": "weighted_linear",
            "assay": "log_expression",
            "parameters": {"signature_mapping_id": mapping["id"]},
            "random_seed": 0,
        },
    )
    assert analysis_created.status_code == 201, analysis_created.text
    configuration = analysis_created.json()["configuration_json"]
    assert configuration["signature_mapping_report_sha256"] == mapping["report_sha256"]
    default_analysis = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "analysis_type": "signature",
            "assay": "log_expression",
            "parameters": {"signature_mapping_id": mapping["id"]},
        },
    )
    assert default_analysis.status_code == 201, default_analysis.text
    assert default_analysis.json()["configuration_json"]["method"] == "mean_z_score"
    association_created = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "name": "Condition-associated cartilage score",
            "analysis_type": "signature",
            "method": "weighted_linear",
            "assay": "log_expression",
            "parameters": {
                "signature_mapping_id": mapping["id"],
                "phenotype_association": {
                    "enabled": True,
                    "phenotype_column": "condition",
                    "block_column": "donor_id",
                },
            },
        },
    )
    assert association_created.status_code == 201, association_created.text
    association_parameters = association_created.json()["configuration_json"]["parameters"]
    assert association_parameters["phenotype_association"] == {
        "enabled": True,
        "phenotype_column": "condition",
        "phenotype_kind": "auto",
        "covariates": [],
        "block_column": "donor_id",
    }
    invalid_association = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "analysis_type": "signature",
            "method": "mean_expression",
            "assay": "log_expression",
            "parameters": {
                "signature_mapping_id": mapping["id"],
                "phenotype_association": {
                    "enabled": True,
                    "phenotype_column": "missing_column",
                },
            },
        },
    )
    assert invalid_association.status_code == 409
    assert "not present" in invalid_association.json()["detail"]
    gsva_created = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "name": "GSVA cartilage score",
            "analysis_type": "signature",
            "method": "gsva",
            "assay": "log_expression",
            "parameters": {
                "signature_mapping_id": mapping["id"],
                "minimum_gene_set_size": 2,
                "maximum_gene_set_size": 100,
                "gsva_kcdf": "Gaussian",
                "gsva_tau": 1.25,
                "gsva_max_diff": True,
                "gsva_abs_ranking": False,
                "ssgsea_alpha": 0.25,
                "ssgsea_normalize": True,
            },
            "random_seed": 0,
        },
    )
    assert gsva_created.status_code == 201, gsva_created.text
    assert gsva_created.json()["configuration_json"]["parameters"]["gsva_tau"] == 1.25
    invalid_size = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "analysis_type": "signature",
            "method": "ssgsea",
            "assay": "log_expression",
            "parameters": {
                "signature_mapping_id": mapping["id"],
                "minimum_gene_set_size": 3,
                "maximum_gene_set_size": 100,
            },
        },
    )
    assert invalid_size.status_code == 409
    assert "outside the configured" in invalid_size.json()["detail"]
    launched = await client.post(f"/api/analyses/{analysis_created.json()['id']}/run")
    assert launched.status_code == 202, launched.text
    assert dispatched_analysis_ids == [launched.json()["id"]]
    async with session_factory() as session:
        run = await session.get(Run, launched.json()["id"])
        assert run is not None
        frozen = json.loads(storage.read_bytes(run.params_uri))
    assert frozen["analysis_type"] == "signature"
    assert frozen["signature_mapping"]["id"] == mapping["id"]
    assert frozen["signature_mapping"]["report_sha256"] == mapping["report_sha256"]
    assert frozen["signature_mapping"]["report"] == report
    score_payload = json.dumps(
        {"analysis_id": analysis_created.json()["id"], "method": "weighted_linear"}
    ).encode()
    stored_scores = storage.put(
        ("tests", "signature-scores", launched.json()["id"]),
        "signature_scores.json",
        BytesIO(score_payload),
    )
    async with session_factory() as session:
        session.add(
            Artifact(
                run_id=launched.json()["id"],
                artifact_type="signature_scores",
                title="Per-sample signature scores",
                relative_path="signature_scores.json",
                storage_uri=stored_scores.uri,
                mime_type="application/json",
                size_bytes=stored_scores.size_bytes,
                sha256=stored_scores.sha256,
                display_order=1,
                metadata_json={},
            )
        )
        await session.commit()
    score_response = await client.get(f"/api/runs/{launched.json()['id']}/signature-scores")
    assert score_response.json() == {
        "analysis_id": analysis_created.json()["id"],
        "method": "weighted_linear",
    }

    listed = await client.get(f"/api/projects/{project_id}/signature-definitions")
    retrieved = await client.get(f"/api/signature-definitions/{definition['id']}")
    assert [item["id"] for item in listed.json()] == [definition["id"]]
    assert retrieved.json()["source_sha256"] == definition["source_sha256"]


async def test_upload_gmt_counts_duplicate_genes_and_rejects_conflicting_weights(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
) -> None:
    project_id, prepared_id = await _prepared_source(session_factory, storage)
    gmt = await client.post(
        f"/api/projects/{project_id}/signature-definitions",
        data={
            "name": "Pathway collection",
            "definition_format": "gmt",
            "identifier_type": "gene_symbol",
        },
        files={"file": ("sets.gmt", b"SET_A\tdemo\tTP53\tEGFR\tTP53\n", "text/plain")},
    )
    assert gmt.status_code == 201, gmt.text
    assert gmt.json()["set_count"] == 1
    assert gmt.json()["duplicate_identifier_count"] == 1
    mapped = await client.post(f"/api/signature-definitions/{gmt.json()['id']}/map/{prepared_id}")
    assert mapped.status_code == 201
    unsupported_weighted = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "analysis_type": "signature",
            "method": "weighted_linear",
            "assay": "log_expression",
            "parameters": {"signature_mapping_id": mapped.json()["id"]},
        },
    )
    assert unsupported_weighted.status_code == 409
    assert "requires a weight" in unsupported_weighted.json()["detail"]

    conflict = await client.post(
        f"/api/projects/{project_id}/signature-definitions",
        data={
            "name": "Conflict",
            "definition_format": "gene_list",
            "identifier_type": "gene_symbol",
        },
        files={"file": ("bad.tsv", b"gene_id\tweight\nTP53\t1\nTP53\t2\n", "text/plain")},
    )
    assert conflict.status_code == 422
    assert "conflicting weights" in conflict.json()["detail"]
