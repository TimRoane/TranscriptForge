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
                value_types_available=["raw_counts", "log_expression", "tpm"],
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
    manifest = json.dumps(
        {
            "organism": "Homo sapiens",
            "sample_metadata": "metadata/sample_metadata.tsv",
            "feature_metadata": "metadata/features.tsv",
            "assays": [
                {
                    "name": "raw_counts",
                    "path": "assays/raw_counts.tsv.gz",
                    "value_type": "nonnegative_integer",
                    "scale": "linear",
                    "feature_level": "gene",
                    "recommended_for": ["differential_expression"],
                    "sha256": "a" * 64,
                },
                {
                    "name": "log_expression",
                    "path": "assays/log_expression.tsv.gz",
                    "value_type": "continuous",
                    "scale": "log2",
                    "feature_level": "gene",
                    "recommended_for": ["signature_analysis", "deconvolution"],
                    "sha256": "b" * 64,
                },
                {
                    "name": "tpm",
                    "path": "assays/tpm.tsv.gz",
                    "value_type": "nonnegative_continuous",
                    "scale": "linear",
                    "feature_level": "gene",
                    "recommended_for": ["deconvolution"],
                    "sha256": "c" * 64,
                },
            ],
        }
    ).encode()
    features = b"feature_id\tgene_symbol\nENSG00000141510\tTP53\nENSG00000146648\tEGFR\n"
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        for name, content in (
            ("expression_bundle/bundle_manifest.json", manifest),
            ("expression_bundle/metadata/sample_metadata.tsv", metadata),
            ("expression_bundle/metadata/features.tsv", features),
        ):
            member = tarfile.TarInfo(name)
            member.size = len(content)
            member.mtime = 0
            archive.addfile(member, BytesIO(content))
    payload.seek(0)
    return payload


async def test_deconvolution_registry_capabilities_and_saved_design(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    dispatched_analysis_ids: list[str],
) -> None:
    prepared_id = await _prepared_dataset(session_factory, storage)

    registry_response = await client.get("/api/deconvolution/methods")
    assert registry_response.status_code == 200
    registry = registry_response.json()
    methods = {item["id"]: item for item in registry["methods"]}
    assert set(methods) == {
        "epic",
        "quantiseq",
        "mcp_counter",
        "xcell",
        "cibersortx_external",
    }
    assert methods["epic"]["result_type"] == "cell_fraction"
    assert methods["quantiseq"]["composition_constraint"] == "sum_to_one_with_other"
    assert methods["mcp_counter"]["result_type"] == "enrichment_score"
    assert methods["xcell"]["within_sample_cell_type_comparison"] is False
    assert methods["cibersortx_external"]["execution_mode"] == "external_import"

    capability_response = await client.get(
        f"/api/prepared-datasets/{prepared_id}/deconvolution/methods"
    )
    assert capability_response.status_code == 200, capability_response.text
    capabilities = {item["method"]["id"]: item for item in capability_response.json()["methods"]}
    assert capabilities["epic"]["compatible_assays"] == ["tpm"]
    assert capabilities["epic"]["configuration_available"] is True
    assert capabilities["epic"]["execution_available"] is False
    assert capabilities["quantiseq"]["execution_available"] is True
    assert capabilities["mcp_counter"]["compatible_assays"] == ["log_expression"]
    assert capabilities["cibersortx_external"]["configuration_available"] is False

    created = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "analysis_type": "deconvolution",
            "method": "epic",
            "assay": "tpm",
            "parameters": {"minimum_gene_overlap": 0.7},
        },
    )
    assert created.status_code == 201, created.text
    configuration = created.json()["configuration_json"]
    assert configuration["parameters"] == {
        "reference_profile": "TRef",
        "minimum_gene_overlap": 0.7,
        "tumor_mode": False,
        "scale_mrna": True,
    }
    assert configuration["method_registry_sha256"] == registry["registry_sha256"]
    assert configuration["method_spec"]["result_type"] == "cell_fraction"
    assert configuration["input_assay_descriptor"]["scale"] == "linear"
    assert configuration["execution_available"] is False

    launch = await client.post(f"/api/analyses/{created.json()['id']}/run")
    assert launch.status_code == 409
    assert "scientific runner is not available" in launch.json()["detail"]
    assert dispatched_analysis_ids == []

    runnable = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "analysis_type": "deconvolution",
            "method": "quantiseq",
            "assay": "tpm",
            "parameters": {"reference_profile": "TIL10", "minimum_gene_overlap": 0.5},
        },
    )
    assert runnable.status_code == 201, runnable.text
    assert runnable.json()["configuration_json"]["execution_available"] is True
    quantiseq_launch = await client.post(f"/api/analyses/{runnable.json()['id']}/run")
    assert quantiseq_launch.status_code == 202, quantiseq_launch.text
    assert dispatched_analysis_ids == [quantiseq_launch.json()["id"]]

    wrong_assay = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "analysis_type": "deconvolution",
            "method": "epic",
            "assay": "log_expression",
        },
    )
    assert wrong_assay.status_code == 409
    assert "cannot use assay 'log_expression'" in wrong_assay.json()["detail"]

    weak_overlap = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "analysis_type": "deconvolution",
            "method": "quantiseq",
            "assay": "tpm",
            "parameters": {"minimum_gene_overlap": 0.4},
        },
    )
    assert weak_overlap.status_code == 409
    assert "at least 50%" in weak_overlap.json()["detail"]

    wrong_reference = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "analysis_type": "deconvolution",
            "method": "quantiseq",
            "assay": "tpm",
            "parameters": {"reference_profile": "TRef"},
        },
    )
    assert wrong_reference.status_code == 409
    assert "Choose one of: TIL10" in wrong_reference.json()["detail"]


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

    numeric_label_block = {
        **request,
        "parameters": {
            **request["parameters"],
            "design": {"primary_variable": "condition", "block_column": "age"},
        },
    }
    numeric_label_preview = await client.post(
        f"/api/prepared-datasets/{prepared_id}/differential-expression/validate-design",
        json=numeric_label_block,
    )
    assert numeric_label_preview.json()["valid"] is True
    assert numeric_label_preview.json()["design_matrix_columns"] == [
        "Intercept",
        "age[44]",
        "condition[treated]",
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
        expression_payload = b"feature_id\tsample_A\tsample_B\ngene_1\t5.1\t7.2\ngene_2\t4.2\t4.0\n"
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
    assert frozen["parameters"]["enrichment"]["enabled"] is False
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

    detail = await client.get(f"/api/runs/{run.id}/differential-expression/features/gene_1")
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

    invalid_enrichment = await client.post(
        f"/api/prepared-datasets/{prepared_id}/differential-expression/validate-design",
        json={
            "assay": "raw_counts",
            "method": "deseq2",
            "parameters": {
                **base_parameters,
                "enrichment": {
                    "enabled": True,
                    "minimum_gene_set_size": 100,
                    "maximum_gene_set_size": 10,
                },
            },
        },
    )
    assert invalid_enrichment.status_code == 422

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
