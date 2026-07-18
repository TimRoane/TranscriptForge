"""Saved analysis configuration, design validation, and durable launch API tests."""

import hashlib
import json
import tarfile
from io import BytesIO

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from transcriptforge_api.models import Analysis, Artifact, Dataset, PreparedDataset, Project, Run
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


async def _classifier_prepared_dataset(
    session_factory: async_sessionmaker[AsyncSession], storage: LocalStorage
) -> str:
    project_id = new_id()
    dataset_id = new_id()
    preparation_run_id = new_id()
    prepared_id = new_id()
    bundle = _classifier_bundle_payload()
    stored = storage.put(("tests", "classifier-bundles"), "expression_bundle.tar.gz", bundle)
    async with session_factory() as session:
        session.add(Project(id=project_id, name="Classifier study", owner_id="local-user"))
        session.add(
            Dataset(
                id=dataset_id,
                project_id=project_id,
                name="Grouped classifier cohort",
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
                params_uri="test://classifier-params",
                output_uri="test://classifier-output",
                work_uri="test://classifier-work",
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
                bundle_manifest_uri="test://classifier-manifest",
                value_types_available=["log_expression"],
                sample_count=24,
                feature_count=1000,
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


def _classifier_bundle_payload() -> BytesIO:
    payload = BytesIO()
    metadata_rows = ["sample_id\tcondition\tsubject_id\tcohort\tsex"]
    for subject in range(1, 13):
        cohort = "site_A" if subject <= 6 else "site_B"
        sex = "female" if subject % 2 else "male"
        metadata_rows.extend(
            [
                f"subject_{subject:02d}_control\tcontrol\tsubject_{subject:02d}\t{cohort}\t{sex}",
                f"subject_{subject:02d}_treated\ttreated\tsubject_{subject:02d}\t{cohort}\t{sex}",
            ]
        )
    metadata = ("\n".join(metadata_rows) + "\n").encode()
    manifest = json.dumps(
        {
            "organism": "Homo sapiens",
            "sample_metadata": "metadata/sample_metadata.tsv",
            "feature_metadata": "metadata/features.tsv",
            "assays": [
                {
                    "name": "log_expression",
                    "path": "assays/log_expression.tsv.gz",
                    "value_type": "continuous",
                    "scale": "log2",
                    "feature_level": "gene",
                    "recommended_for": ["classifier"],
                    "sha256": "a" * 64,
                }
            ],
        }
    ).encode()
    features = b"feature_id\tgene_symbol\nENSG00000141510\tTP53\n"
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


async def _multiclass_prepared_dataset(
    session_factory: async_sessionmaker[AsyncSession], storage: LocalStorage
) -> str:
    project_id = new_id()
    dataset_id = new_id()
    run_id = new_id()
    prepared_id = new_id()
    payload = BytesIO()
    metadata_rows = ["sample_id\tsubtype\tsubject_id\tcohort"]
    for subject in range(1, 13):
        for subtype in ("basal", "immune", "luminal"):
            metadata_rows.append(
                f"subject_{subject:02d}_{subtype}\t{subtype}\tsubject_{subject:02d}\t"
                f"site_{'A' if subject <= 6 else 'B'}"
            )
    manifest = json.dumps(
        {
            "organism": "Homo sapiens",
            "sample_metadata": "metadata/sample_metadata.tsv",
            "feature_metadata": "metadata/features.tsv",
            "assays": [
                {
                    "name": "log_expression",
                    "path": "assays/log_expression.tsv.gz",
                    "value_type": "continuous",
                    "scale": "log2",
                    "feature_level": "gene",
                    "recommended_for": ["classifier"],
                    "sha256": "a" * 64,
                }
            ],
        }
    ).encode()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        for name, content in (
            (
                "expression_bundle/bundle_manifest.json",
                manifest,
            ),
            (
                "expression_bundle/metadata/sample_metadata.tsv",
                ("\n".join(metadata_rows) + "\n").encode(),
            ),
            ("expression_bundle/metadata/features.tsv", b"feature_id\tgene_symbol\nG1\tG1\n"),
        ):
            member = tarfile.TarInfo(name)
            member.size = len(content)
            member.mtime = 0
            archive.addfile(member, BytesIO(content))
    payload.seek(0)
    stored = storage.put(("tests", "multiclass-bundles"), "expression_bundle.tar.gz", payload)
    async with session_factory() as session:
        session.add(Project(id=project_id, name="Multiclass study", owner_id="local-user"))
        session.add(
            Dataset(
                id=dataset_id,
                project_id=project_id,
                name="Grouped multiclass cohort",
                modality="bulk_rnaseq",
                source_kind="count_matrix",
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
                params_uri="test://multiclass-params",
                output_uri="test://multiclass-output",
                work_uri="test://multiclass-work",
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
                bundle_manifest_uri="test://multiclass-manifest",
                value_types_available=["log_expression"],
                sample_count=36,
                feature_count=1000,
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
    return prepared_id


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
    assert capabilities["mcp_counter"]["execution_available"] is True
    assert capabilities["xcell"]["execution_available"] is True
    assert capabilities["cibersortx_external"]["configuration_available"] is True
    assert capabilities["cibersortx_external"]["compatible_assays"] == ["tpm"]
    assert capabilities["cibersortx_external"]["execution_available"] is False

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
    assert "does not have a native scientific runner" in launch.json()["detail"]
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

    enrichment = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "analysis_type": "deconvolution",
            "method": "mcp_counter",
            "assay": "log_expression",
            "parameters": {
                "reference_profile": "MCPcounter_v1",
                "minimum_gene_overlap": 0.5,
            },
        },
    )
    assert enrichment.status_code == 201, enrichment.text
    enrichment_configuration = enrichment.json()["configuration_json"]
    assert enrichment_configuration["result_type"] == "enrichment_score"
    assert enrichment_configuration["execution_available"] is True
    enrichment_launch = await client.post(f"/api/analyses/{enrichment.json()['id']}/run")
    assert enrichment_launch.status_code == 202, enrichment_launch.text
    assert dispatched_analysis_ids == [
        quantiseq_launch.json()["id"],
        enrichment_launch.json()["id"],
    ]

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


async def test_deconvolution_comparison_separates_semantics_and_matches_exact_populations(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
) -> None:
    prepared_id = await _prepared_dataset(session_factory, storage)
    sample_ids = ["sample_A", "sample_B", "sample_C", "sample_D"]

    async def add_result(
        *,
        method: str,
        display_name: str,
        result_type: str,
        unit: str,
        composition_constraint: str,
        assay: dict[str, str],
        reference_id: str,
        cell_types: list[tuple[str, str]],
        values: dict[str, list[float]],
        malformed: bool = False,
    ) -> tuple[str, str]:
        analysis_id = new_id()
        run_id = new_id()
        payload = {
            "prepared_dataset_id": prepared_id,
            "method": method,
            "method_registry_version": "2026.07.2",
            "method_registry_sha256": "a" * 64,
            "result_type": result_type,
            "quantity_label": "Estimated fraction"
            if result_type == "cell_fraction"
            else "Cell-population abundance score",
            "unit": unit,
            "composition_constraint": composition_constraint,
            "input_validation": {
                **assay,
                "feature_level": "gene",
                "identifier_namespace": "gene_symbol",
                "overlap_fraction": 0.9,
            },
            "reference": {
                "id": reference_id,
                "version": f"{reference_id}-test",
                "sha256": "b" * 64,
            },
            "sample_ids": sample_ids,
            "cell_types": [{"id": item[0], "label": item[1]} for item in cell_types],
            "estimates": [
                {
                    "sample_id": sample_id,
                    "cell_type_id": cell_type_id,
                    "value": values[cell_type_id][sample_index],
                }
                for sample_index, sample_id in enumerate(sample_ids)
                for cell_type_id, _ in cell_types
            ],
            "provenance": {"expression_bundle_sha256": "c" * 64},
        }
        source = b"not-json" if malformed else json.dumps(payload).encode()
        stored = storage.put(
            ("tests", "deconvolution-comparison", run_id),
            "deconvolution_results.json",
            BytesIO(source),
        )
        async with session_factory() as session:
            prepared = await session.get(PreparedDataset, prepared_id)
            assert prepared is not None
            dataset = await session.get(Dataset, prepared.dataset_id)
            assert dataset is not None
            session.add(
                Analysis(
                    id=analysis_id,
                    project_id=dataset.project_id,
                    prepared_dataset_id=prepared_id,
                    analysis_type="deconvolution",
                    name=f"{display_name} comparison",
                    description=None,
                    configuration_json={"method_spec": {"display_name": display_name}},
                )
            )
            await session.flush()
            session.add(
                Run(
                    id=run_id,
                    run_type="analysis",
                    dataset_id=prepared.dataset_id,
                    prepared_dataset_id=prepared_id,
                    analysis_id=analysis_id,
                    state="SUCCEEDED",
                    profile="test",
                    params_uri=f"test://{run_id}/params",
                    output_uri=f"test://{run_id}/output",
                    work_uri=f"test://{run_id}/work",
                )
            )
            await session.flush()
            session.add(
                Artifact(
                    run_id=run_id,
                    artifact_type="deconvolution_results",
                    title="Structured cell-population results",
                    relative_path="deconvolution_results.json",
                    storage_uri=stored.uri,
                    mime_type="application/json",
                    size_bytes=stored.size_bytes,
                    sha256=stored.sha256,
                    display_order=1,
                    metadata_json={},
                )
            )
            await session.commit()
        return analysis_id, run_id

    log_assay = {"assay": "log_expression", "scale": "log2", "value_type": "continuous"}
    mcp_analysis_id, mcp_run_id = await add_result(
        method="mcp_counter",
        display_name="MCP-counter",
        result_type="enrichment_score",
        unit="arbitrary_score",
        composition_constraint="not_compositional",
        assay=log_assay,
        reference_id="MCPcounter_v1",
        cell_types=[("NK cells", "NK cells"), ("Fibroblasts", "Fibroblasts")],
        values={"NK cells": [1, 2, 3, 4], "Fibroblasts": [4, 3, 2, 1]},
    )
    _, xcell_run_id = await add_result(
        method="xcell",
        display_name="xCell",
        result_type="enrichment_score",
        unit="arbitrary_score",
        composition_constraint="not_compositional",
        assay=log_assay,
        reference_id="xCell_v1",
        cell_types=[
            ("NK cells", "NK cells"),
            ("Fibroblasts", "Fibroblasts"),
            ("B-cells", "B cells"),
        ],
        values={
            "NK cells": [2, 4, 6, 8],
            "Fibroblasts": [8, 6, 4, 2],
            "B-cells": [1, 1, 2, 2],
        },
    )
    await add_result(
        method="quantiseq",
        display_name="quanTIseq",
        result_type="cell_fraction",
        unit="fraction",
        composition_constraint="sum_to_one_with_other",
        assay={"assay": "tpm", "scale": "linear", "value_type": "nonnegative_continuous"},
        reference_id="TIL10",
        cell_types=[("B.cells", "B cells")],
        values={"B.cells": [0.1, 0.2, 0.3, 0.4]},
    )
    invalid_analysis_id, invalid_run_id = await add_result(
        method="mcp_counter",
        display_name="Broken MCP-counter",
        result_type="enrichment_score",
        unit="arbitrary_score",
        composition_constraint="not_compositional",
        assay=log_assay,
        reference_id="MCPcounter_v1",
        cell_types=[("NK cells", "NK cells")],
        values={"NK cells": [1, 2, 3, 4]},
        malformed=True,
    )

    response = await client.get(f"/api/prepared-datasets/{prepared_id}/deconvolution/comparison")
    assert response.status_code == 200, response.text
    comparison = response.json()
    assert comparison["latest_successful_run_count"] == 4
    assert len(comparison["sections"]) == 2
    enrichment = next(
        section
        for section in comparison["sections"]
        if section["result_type"] == "enrichment_score"
    )
    assert [run["method"] for run in enrichment["runs"]] == ["mcp_counter", "xcell"]
    assert enrichment["assay"] == {
        "name": "log_expression",
        "scale": "log2",
        "value_type": "continuous",
        "feature_level": "gene",
        "identifier_namespace": "gene_symbol",
    }
    assert [item["id"] for item in enrichment["shared_cell_types"]] == [
        "NK cells",
        "Fibroblasts",
    ]
    nk = next(item for item in enrichment["correlations"] if item["cell_type_id"] == "NK cells")
    assert nk["left_run_id"] in {mcp_run_id, xcell_run_id}
    assert nk["right_run_id"] in {mcp_run_id, xcell_run_id}
    assert nk["pearson_correlation"] == 1.0
    assert any("reference crosswalk" in warning for warning in enrichment["warnings"])
    fraction = next(
        section for section in comparison["sections"] if section["result_type"] == "cell_fraction"
    )
    assert len(fraction["runs"]) == 1
    assert fraction["correlations"] == []
    assert comparison["exclusions"] == [
        {
            "analysis_id": invalid_analysis_id,
            "analysis_name": "Broken MCP-counter comparison",
            "run_id": invalid_run_id,
            "reason": (
                "Result artifact is not comparison-ready: Expecting value: line 1 column 1 (char 0)"
            ),
        }
    ]
    assert any(run["analysis_id"] == mcp_analysis_id for run in enrichment["runs"])


async def test_cibersortx_external_relative_fraction_import_is_audited(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
) -> None:
    prepared_id = await _prepared_dataset(session_factory, storage)
    source = (
        b"Mixture\tB cells\tCD8 T cells\tP-value\tCorrelation\tRMSE\n"
        b"sample_C\t0.2\t0.8\t0.01\t0.9\t0.1\n"
        b"sample_A\t0.7\t0.3\t0.01\t0.9\t0.1\n"
        b"sample_D\t0.4\t0.6\t0.01\t0.9\t0.1\n"
        b"sample_B\t0.6\t0.4\t0.01\t0.9\t0.1\n"
    )
    metadata = {
        "analysis_name": "Imported CIBERSORTx immune fractions",
        "assay": "tpm",
        "mode": "relative",
        "fractions_declared": True,
        "batch_correction": "B-mode",
        "permutations": 100,
        "mixture_gene_count": 18_000,
        "overlap_gene_count": 500,
        "signature": {
            "name": "LM22",
            "version": "custom-2026-07",
            "sha256": "d" * 64,
            "gene_count": 547,
        },
        "runtime": {
            "version": "CIBERSORTx-2026-05",
            "external_run_id": "stanford-job-123",
            "executed_at": "2026-07-17T20:30:00Z",
        },
    }
    response = await client.post(
        f"/api/prepared-datasets/{prepared_id}/deconvolution/cibersortx-imports",
        data={"metadata": json.dumps(metadata)},
        files={"file": ("CIBERSORTx_Results.txt", source, "text/plain")},
    )
    assert response.status_code == 201, response.text
    analysis = response.json()
    assert analysis["name"] == "Imported CIBERSORTx immune fractions"
    configuration = analysis["configuration_json"]
    assert configuration["method"] == "cibersortx_external"
    assert configuration["execution_available"] is False
    assert configuration["method_spec"]["execution_mode"] == "external_import"
    assert configuration["external_import"]["source_sha256"] == hashlib.sha256(source).hexdigest()
    native_launch = await client.post(f"/api/analyses/{analysis['id']}/run")
    assert native_launch.status_code == 409
    assert "does not have a native scientific runner" in native_launch.json()["detail"]

    runs_response = await client.get(f"/api/analyses/{analysis['id']}/runs")
    assert runs_response.status_code == 200
    runs = runs_response.json()
    assert len(runs) == 1
    run = runs[0]
    assert run["state"] == "SUCCEEDED"
    assert run["profile"] == "external_import"
    result_response = await client.get(f"/api/runs/{run['id']}/deconvolution-results")
    assert result_response.status_code == 200
    result = result_response.json()
    assert result["method"] == "cibersortx_external"
    assert result["composition_constraint"] == "declared_by_import"
    assert result["sample_ids"] == ["sample_A", "sample_B", "sample_C", "sample_D"]
    assert result["external_import"]["mode"] == "relative"
    assert result["external_import"]["signature"]["sha256"] == "d" * 64
    assert result["provenance"]["external_source_sha256"] == hashlib.sha256(source).hexdigest()
    assert all(item["within_tolerance"] for item in result["composition_summaries"])

    artifacts_response = await client.get(f"/api/runs/{run['id']}/artifacts")
    assert artifacts_response.status_code == 200
    artifacts = artifacts_response.json()
    assert {item["artifact_type"] for item in artifacts} == {
        "result_manifest",
        "deconvolution_results",
        "deconvolution_estimates",
        "cibersortx_source",
        "external_import_provenance",
    }
    source_artifact = next(
        item for item in artifacts if item["artifact_type"] == "cibersortx_source"
    )
    downloaded = await client.get(f"/api/artifacts/{source_artifact['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == source

    comparison_response = await client.get(
        f"/api/prepared-datasets/{prepared_id}/deconvolution/comparison"
    )
    assert comparison_response.status_code == 200
    comparison = comparison_response.json()
    assert comparison["latest_successful_run_count"] == 1
    assert comparison["sections"][0]["runs"][0]["method"] == "cibersortx_external"

    missing_sample = source.replace(
        b"sample_B\t0.6\t0.4\t0.01\t0.9\t0.1\n",
        b"",
    )
    rejected = await client.post(
        f"/api/prepared-datasets/{prepared_id}/deconvolution/cibersortx-imports",
        data={"metadata": json.dumps(metadata)},
        files={"file": ("incomplete.tsv", missing_sample, "text/tab-separated-values")},
    )
    assert rejected.status_code == 422
    assert "missing: sample_B" in rejected.json()["detail"]

    undeclared = {**metadata, "fractions_declared": False}
    declaration_response = await client.post(
        f"/api/prepared-datasets/{prepared_id}/deconvolution/cibersortx-imports",
        data={"metadata": json.dumps(undeclared)},
        files={"file": ("result.tsv", source, "text/tab-separated-values")},
    )
    assert declaration_response.status_code == 422
    assert "explicitly declared as relative fractions" in declaration_response.json()["detail"]


async def test_classifier_design_freezes_grouped_nested_cv_and_queues_execution(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    dispatched_analysis_ids: list[str],
) -> None:
    prepared_id = await _classifier_prepared_dataset(session_factory, storage)
    options_response = await client.get(
        f"/api/prepared-datasets/{prepared_id}/classifier/design-options"
    )
    assert options_response.status_code == 200
    options = options_response.json()
    assert options["sample_count"] == 24
    assert {item["name"] for item in options["variables"]} >= {
        "condition",
        "subject_id",
        "cohort",
    }
    parameters = {
        "outcome_column": "condition",
        "positive_class": "treated",
        "group_column": "subject_id",
        "cohort_column": "cohort",
        "top_variable_features": 500,
        "class_weight": "balanced",
        "outer_folds": 3,
        "inner_folds": 2,
        "repeats": 2,
        "primary_metric": "roc_auc",
        "probability_calibration": "none",
        "decision_threshold_strategy": "fixed_0_5",
        "bootstrap_iterations": 1000,
        "permutation_count": 100,
    }
    preview_request = {
        "assay": "log_expression",
        "method": "elastic_net",
        "parameters": parameters,
        "random_seed": 20260717,
    }
    preview_response = await client.post(
        f"/api/prepared-datasets/{prepared_id}/classifier/validate-design",
        json=preview_request,
    )
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    assert preview["valid"] is True, preview["errors"]
    assert preview["class_counts"] == {"control": 12, "treated": 12}
    assert preview["group_count"] == 12
    assert preview["expected_oof_prediction_count"] == 48
    assert preview["preprocessing_scope"] == "fit_inside_each_training_fold"
    assert preview["tuning_scope"] == "inner_training_folds_only"
    assert len(preview["fold_plan"]) == 6
    assert all(item["group_overlap_count"] == 0 for item in preview["fold_plan"])
    assert all(
        set(item["test_class_counts"]) == {"control", "treated"} for item in preview["fold_plan"]
    )

    repeated_response = await client.post(
        f"/api/prepared-datasets/{prepared_id}/classifier/validate-design",
        json=preview_request,
    )
    assert repeated_response.status_code == 200
    assert repeated_response.json()["fold_plan"] == preview["fold_plan"]

    ungrouped = {
        **preview_request,
        "parameters": {**parameters, "group_column": None},
    }
    ungrouped_response = await client.post(
        f"/api/prepared-datasets/{prepared_id}/classifier/validate-design",
        json=ungrouped,
    )
    assert ungrouped_response.status_code == 200
    assert ungrouped_response.json()["valid"] is False
    assert any(
        "Repeated experimental-unit column 'subject_id'" in error
        for error in ungrouped_response.json()["errors"]
    )

    created_response = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={
            "analysis_type": "classifier",
            "name": "Treatment elastic-net classifier",
            **preview_request,
        },
    )
    assert created_response.status_code == 201, created_response.text
    analysis = created_response.json()
    configuration = analysis["configuration_json"]
    assert configuration["method"] == "elastic_net"
    assert configuration["execution_available"] is True
    assert configuration["design_validation"]["fold_plan"] == preview["fold_plan"]
    assert configuration["leakage_policy"] == {
        "preprocessing_scope": "fit_inside_each_training_fold",
        "feature_selection_scope": "fit_inside_each_training_fold",
        "hyperparameter_tuning_scope": "inner_training_folds_only",
        "outer_test_fold_role": "evaluation_only",
    }
    launch_response = await client.post(f"/api/analyses/{analysis['id']}/run")
    assert launch_response.status_code == 202, launch_response.text
    assert dispatched_analysis_ids == [launch_response.json()["id"]]


async def test_multiclass_classifier_design_freezes_all_class_folds(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
) -> None:
    prepared_id = await _multiclass_prepared_dataset(session_factory, storage)
    parameters = {
        "outcome_column": "subtype",
        "positive_class": None,
        "group_column": "subject_id",
        "cohort_column": "cohort",
        "top_variable_features": 500,
        "class_weight": "balanced",
        "outer_folds": 3,
        "inner_folds": 2,
        "repeats": 2,
        "primary_metric": "macro_roc_auc",
        "probability_calibration": "none",
        "decision_threshold_strategy": "fixed_0_5",
        "bootstrap_iterations": 1000,
        "permutation_count": 100,
    }
    request = {
        "assay": "log_expression",
        "method": "multinomial_elastic_net",
        "parameters": parameters,
        "random_seed": 20260718,
    }
    response = await client.post(
        f"/api/prepared-datasets/{prepared_id}/classifier/validate-design", json=request
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["valid"] is True, preview["errors"]
    assert preview["positive_class"] is None
    assert preview["negative_class"] is None
    assert preview["class_labels"] == ["basal", "immune", "luminal"]
    assert preview["expected_oof_prediction_count"] == 72
    assert all(
        set(fold["training_class_counts"]) == {"basal", "immune", "luminal"}
        and set(fold["test_class_counts"]) == {"basal", "immune", "luminal"}
        and fold["group_overlap_count"] == 0
        for fold in preview["fold_plan"]
    )

    created = await client.post(
        f"/api/prepared-datasets/{prepared_id}/analyses",
        json={"analysis_type": "classifier", "name": "Subtype classifier", **request},
    )
    assert created.status_code == 201, created.text
    assert created.json()["configuration_json"]["method"] == "multinomial_elastic_net"

    invalid = await client.post(
        f"/api/prepared-datasets/{prepared_id}/classifier/validate-design",
        json={
            **request,
            "parameters": {
                **parameters,
                "positive_class": "basal",
                "primary_metric": "roc_auc",
            },
        },
    )
    assert invalid.status_code == 200
    assert invalid.json()["valid"] is False


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
