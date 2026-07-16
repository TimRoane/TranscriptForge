"""Saved analysis configuration, design validation, and durable launch API tests."""

import json
import tarfile
from io import BytesIO

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from transcriptforge_api.models import Artifact, Dataset, PreparedDataset, Project, Run
from transcriptforge_api.models.base import new_id
from transcriptforge_api.storage.local import LocalStorage


async def _prepared_dataset(
    session_factory: async_sessionmaker[AsyncSession], storage: LocalStorage
) -> str:
    project_id = new_id()
    dataset_id = new_id()
    preparation_run_id = new_id()
    prepared_id = new_id()
    stored = storage.put(("tests", "bundles"), "expression_bundle.tar.gz", _bundle_payload())
    async with session_factory() as session:
        session.add(Project(id=project_id, name="PCA study", owner_id="local-user"))
        session.add(
            Dataset(
                id=dataset_id,
                project_id=project_id,
                name="PCA counts",
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
                preparation_run_id=preparation_run_id,
                bundle_uri=stored.uri,
                bundle_manifest_uri="test://manifest",
                value_types_available=["raw_counts", "log_expression"],
                sample_count=4,
                feature_count=5,
                qc_status="PASS",
            )
        )
        session.add(
            Artifact(
                run_id=preparation_run_id,
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
    return prepared_id


def _bundle_payload() -> BytesIO:
    payload = BytesIO()
    metadata = (
        b"sample_id\tcondition\tduplicate_condition\tbatch\tdonor_id\tage\n"
        b"sample_A\tcontrol\tcontrol\tbatch_1\tdonor_1\t40\n"
        b"sample_B\ttreated\ttreated\tbatch_1\tdonor_1\t40\n"
        b"sample_C\tcontrol\tcontrol\tbatch_2\tdonor_2\t44\n"
        b"sample_D\ttreated\ttreated\tbatch_2\tdonor_2\t44\n"
    )
    manifest = json.dumps({"sample_metadata": "metadata/sample_metadata.tsv"}).encode()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        for name, content in (
            ("expression_bundle/bundle_manifest.json", manifest),
            ("expression_bundle/metadata/sample_metadata.tsv", metadata),
        ):
            member = tarfile.TarInfo(name)
            member.size = len(content)
            member.mtime = 0
            archive.addfile(member, BytesIO(content))
    payload.seek(0)
    return payload


async def test_create_launch_list_and_clone_pca_analysis(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    dispatched_analysis_ids: list[str],
) -> None:
    prepared_id = await _prepared_dataset(session_factory, storage)
    created = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "name": "Study PCA",
            "assay": "log_expression",
            "parameters": {"component_count": 3, "scale_features": True},
            "random_seed": 7,
        },
    )
    assert created.status_code == 201
    analysis = created.json()
    assert analysis["analysis_type"] == "dimension_reduction"
    assert analysis["configuration_json"]["method"] == "pca"

    launched = await client.post(f"/api/analyses/{analysis['id']}/run")
    assert launched.status_code == 202
    run = launched.json()
    assert run["run_type"] == "analysis"
    assert run["analysis_id"] == analysis["id"]
    assert run["prepared_dataset_id"] == prepared_id
    assert dispatched_analysis_ids == [run["id"]]

    listed = await client.get(f"/api/analyses/{analysis['id']}/runs")
    assert [item["id"] for item in listed.json()] == [run["id"]]
    duplicate = await client.post(f"/api/analyses/{analysis['id']}/run")
    assert duplicate.status_code == 409
    clone = await client.post(f"/api/analyses/{analysis['id']}/clone")
    assert clone.status_code == 201
    assert clone.json()["name"] == "Study PCA (copy)"


async def test_pca_rejects_an_unavailable_assay(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
) -> None:
    prepared_id = await _prepared_dataset(session_factory, storage)
    response = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={"assay": "vst_expression"},
    )
    assert response.status_code == 409
    assert "not available" in response.json()["detail"]


async def test_stochastic_embedding_parameters_are_checked_against_sample_count(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
) -> None:
    prepared_id = await _prepared_dataset(session_factory, storage)

    umap = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={"method": "umap", "parameters": {"neighbors": 4}},
    )
    tsne = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={"method": "tsne", "parameters": {"perplexity": 4}},
    )

    assert umap.status_code == 409
    assert "smaller than the number of samples" in umap.json()["detail"]
    assert tsne.status_code == 409
    assert "smaller than the number of samples" in tsne.json()["detail"]


async def test_hierarchical_clustering_configuration_is_saved(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
) -> None:
    prepared_id = await _prepared_dataset(session_factory, storage)
    response = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "name": "Sample clusters",
            "method": "hierarchical_clustering",
            "parameters": {
                "top_variable_features": 250,
                "distance_metric": "correlation",
                "linkage_method": "average",
                "cluster_count": 3,
            },
        },
    )

    assert response.status_code == 201
    configuration = response.json()["configuration_json"]
    assert configuration["method"] == "hierarchical_clustering"
    assert configuration["parameters"]["cluster_count"] == 3


async def test_differential_expression_design_options_and_validated_save(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    dispatched_analysis_ids: list[str],
) -> None:
    prepared_id = await _prepared_dataset(session_factory, storage)
    options = await client.get(
        f"/api/prepared-datasets/{prepared_id}/differential-expression/design-options"
    )
    assert options.status_code == 200
    variables = {item["name"]: item for item in options.json()["variables"]}
    assert variables["condition"]["levels"] == ["control", "treated"]
    assert variables["age"]["kind"] == "numeric"

    request = {
        "assay": "raw_counts",
        "method": "auto",
        "parameters": {
            "design": {"primary_variable": "condition", "covariates": ["batch"]},
            "contrast": {
                "variable": "condition",
                "numerator": "treated",
                "denominator": "control",
            },
        },
    }
    preview = await client.post(
        f"/api/prepared-datasets/{prepared_id}/differential-expression/validate-design",
        json=request,
    )
    assert preview.status_code == 200
    assert preview.json()["valid"] is True
    assert preview.json()["resolved_method"] == "deseq2"
    assert preview.json()["formula"] == "~ batch + condition"
    assert preview.json()["contrast_counts"] == {"treated": 2, "control": 2}

    paired_request = {
        **request,
        "parameters": {
            **request["parameters"],
            "design": {"primary_variable": "condition", "block_column": "donor_id"},
        },
    }
    paired = await client.post(
        f"/api/prepared-datasets/{prepared_id}/differential-expression/validate-design",
        json=paired_request,
    )
    assert paired.json()["valid"] is True
    assert paired.json()["formula"] == "~ donor_id + condition"
    assert paired.json()["design_cells"] == [
        {"values": {"condition": "control"}, "sample_count": 2},
        {"values": {"condition": "treated"}, "sample_count": 2},
    ]

    created = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "name": "Treatment response",
            "analysis_type": "differential_expression",
            **request,
        },
    )
    assert created.status_code == 201
    configuration = created.json()["configuration_json"]
    assert configuration["method"] == "deseq2"
    assert configuration["design_formula"] == "~ batch + condition"
    assert configuration["contrast_label"] == "treated versus control within condition"

    launch = await client.post(f"/api/analyses/{created.json()['id']}/run")
    assert launch.status_code == 202
    assert launch.json()["analysis_id"] == created.json()["id"]
    assert dispatched_analysis_ids == [launch.json()["id"]]
    async with session_factory() as session:
        run = await session.get(Run, launch.json()["id"])
        assert run is not None
        frozen = json.loads(storage.read_bytes(run.params_uri))
        plot_contracts = {
            "p_value_distribution": {
                "schema_version": "1.0.0",
                "analysis_id": created.json()["id"],
                "bins": [{"start": 0, "end": 0.05, "count": 5}],
            },
            "expression_heatmap": {
                "schema_version": "1.0.0",
                "analysis_id": created.json()["id"],
                "feature_ids": ["gene_1"],
                "sample_ids": ["sample_A", "sample_B"],
                "values": [[-1, 1]],
                "assay": "raw_counts",
                "source": "log2 DESeq2 normalized count + 1",
                "metadata": {
                    "sample_A": {"condition": "control", "batch": "batch_1"},
                    "sample_B": {"condition": "treated", "batch": "batch_1"},
                },
                "contrast": {
                    "variable": "condition",
                    "numerator": "treated",
                    "denominator": "control",
                },
            },
        }
        for display_order, (artifact_type, contract) in enumerate(plot_contracts.items()):
            payload = json.dumps(contract).encode()
            stored = storage.put(
                ("tests", "analysis-plots", run.id),
                f"{artifact_type}.json",
                BytesIO(payload),
            )
            session.add(
                Artifact(
                    run_id=run.id,
                    artifact_type=artifact_type,
                    title=artifact_type.replace("_", " ").title(),
                    relative_path=f"{artifact_type}.json",
                    storage_uri=stored.uri,
                    mime_type="application/json",
                    size_bytes=stored.size_bytes,
                    sha256=stored.sha256,
                    display_order=display_order,
                    metadata_json={},
                )
            )
        table_payload = (
            b"feature_id\tgene_symbol\tbase_mean\tlog2_fold_change\tstandard_error\t"
            b"statistic\tp_value\tadjusted_p_value\tcontrast\tmethod\tsignificant\n"
            b"gene_1\tABC1\t100\t1.5\t0.2\t7.5\t0.0001\t0.001\t"
            b"treated versus control\tDESeq2\tTRUE\n"
            b"gene_2\tXYZ2\t20\t-0.2\t0.3\t-0.67\t0.5\t0.8\t"
            b"treated versus control\tDESeq2\tFALSE\n"
        )
        expression_payload = (
            b"feature_id\tsample_A\tsample_B\n"
            b"gene_1\t5.1\t7.2\n"
            b"gene_2\t4.2\t4.0\n"
        )
        for display_order, (artifact_type, payload) in enumerate(
            (
                ("differential_expression_results", table_payload),
                ("normalized_expression", expression_payload),
            ),
            start=2,
        ):
            stored = storage.put(
                ("tests", "analysis-plots", run.id), f"{artifact_type}.tsv", BytesIO(payload)
            )
            session.add(
                Artifact(
                    run_id=run.id,
                    artifact_type=artifact_type,
                    title=artifact_type.replace("_", " ").title(),
                    relative_path=f"{artifact_type}.tsv",
                    storage_uri=stored.uri,
                    mime_type="text/tab-separated-values",
                    size_bytes=stored.size_bytes,
                    sha256=stored.sha256,
                    display_order=display_order,
                    metadata_json={},
                )
            )
        await session.commit()
    assert frozen["design_formula"] == "~ batch + condition"
    assert frozen["design_validation"]["design_matrix_rank"] == 3
    p_values = await client.get(f"/api/runs/{run.id}/p-value-distribution")
    heatmap = await client.get(f"/api/runs/{run.id}/expression-heatmap")
    assert p_values.json()["bins"][0]["count"] == 5
    assert heatmap.json()["feature_ids"] == ["gene_1"]
    results = await client.get(
        f"/api/runs/{run.id}/differential-expression/results",
        params={"search": "abc", "fdr_max": 0.05, "absolute_log2_fold_change_min": 1},
    )
    assert results.status_code == 200
    assert results.json()["total"] == 1
    assert results.json()["items"][0]["gene_symbol"] == "ABC1"
    assert results.json()["base_expression_label"] == "Base mean normalized count"

    descending = await client.get(
        f"/api/runs/{run.id}/differential-expression/results",
        params={"sort_by": "log2_fold_change", "direction": "desc", "limit": 1},
    )
    assert descending.json()["items"][0]["feature_id"] == "gene_1"
    filtered_download = await client.get(
        f"/api/runs/{run.id}/differential-expression/results.tsv",
        params={"significant_only": True},
    )
    assert filtered_download.status_code == 200
    assert "gene_1" in filtered_download.text
    assert "gene_2" not in filtered_download.text

    detail = await client.get(
        f"/api/runs/{run.id}/differential-expression/features/gene_1"
    )
    assert detail.status_code == 200
    assert detail.json()["result"]["gene_symbol"] == "ABC1"
    assert [item["level"] for item in detail.json()["expression_profile"]["group_summaries"]] == [
        "control",
        "treated",
    ]
    assert detail.json()["expression_profile"]["values"][1]["value"] == 7.2
    missing_detail = await client.get(
        f"/api/runs/{run.id}/differential-expression/features/not_a_gene"
    )
    assert missing_detail.status_code == 404

    limma_request = {**request, "assay": "log_expression", "method": "auto"}
    limma_created = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "name": "Treatment response on log expression",
            "analysis_type": "differential_expression",
            **limma_request,
        },
    )
    assert limma_created.status_code == 201
    assert limma_created.json()["configuration_json"]["method"] == "limma"
    limma_launch = await client.post(f"/api/analyses/{limma_created.json()['id']}/run")
    assert limma_launch.status_code == 202
    assert dispatched_analysis_ids == [launch.json()["id"], limma_launch.json()["id"]]


async def test_differential_expression_rejects_incompatible_and_rank_deficient_designs(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
) -> None:
    prepared_id = await _prepared_dataset(session_factory, storage)
    base_parameters = {
        "design": {
            "primary_variable": "condition",
            "covariates": ["duplicate_condition"],
        },
        "contrast": {
            "variable": "condition",
            "numerator": "treated",
            "denominator": "control",
        },
    }
    preview = await client.post(
        f"/api/prepared-datasets/{prepared_id}/differential-expression/validate-design",
        json={"assay": "raw_counts", "method": "limma", "parameters": base_parameters},
    )
    assert preview.status_code == 200
    assert preview.json()["valid"] is False
    assert any("incompatible" in message for message in preview.json()["errors"])
    assert any("rank deficient" in message for message in preview.json()["errors"])

    created = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "analysis_type": "differential_expression",
            "assay": "raw_counts",
            "method": "auto",
            "parameters": base_parameters,
        },
    )
    assert created.status_code == 409
    assert "rank deficient" in created.json()["detail"]


async def test_count_assay_supports_edger_ql_and_limma_voom(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
) -> None:
    prepared_id = await _prepared_dataset(session_factory, storage)
    parameters = {
        "design": {"primary_variable": "condition"},
        "contrast": {
            "variable": "condition",
            "numerator": "treated",
            "denominator": "control",
        },
    }
    for method in ("edger_ql", "limma_voom"):
        preview = await client.post(
            f"/api/prepared-datasets/{prepared_id}/differential-expression/validate-design",
            json={"assay": "raw_counts", "method": method, "parameters": parameters},
        )
        assert preview.status_code == 200
        assert preview.json()["valid"] is True
        assert preview.json()["resolved_method"] == method

        created = await client.post(
            f"/api/prepared-datasets/{prepared_id}/analyses",
            json={
                "name": f"Treatment response with {method}",
                "analysis_type": "differential_expression",
                "assay": "raw_counts",
                "method": method,
                "parameters": parameters,
            },
        )
        assert created.status_code == 201
        assert created.json()["configuration_json"]["method"] == method

    incompatible = await client.post(
        f"/api/prepared-datasets/{prepared_id}/differential-expression/validate-design",
        json={"assay": "log_expression", "method": "edger_ql", "parameters": parameters},
    )
    assert incompatible.status_code == 200
    assert incompatible.json()["valid"] is False
    assert any("incompatible" in message for message in incompatible.json()["errors"])
