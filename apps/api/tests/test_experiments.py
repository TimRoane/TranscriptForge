"""API lifecycle coverage for the first pre-lock Development Experiment."""

import json
import tarfile
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from transcriptforge_api.models import Artifact, Dataset, PreparedDataset, Recommendation, Run
from transcriptforge_api.storage.local import LocalStorage

from demo.assay_development.generate_multifactor_fixture import generate as generate_multifactor


def _assignments(*, confounded: bool) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sample_index, biological_sample in enumerate(("bio-1", "bio-2"), start=1):
        for input_ng, suffix, dv200 in ((100, "100", 72), (50, "50", 61), (25, "25", 49)):
            rows.append(
                {
                    "measurement_id": f"s{sample_index}_{suffix}",
                    "biological_sample_id": biological_sample,
                    "prepared_dataset_id": "prepared-ffpe",
                    "include": True,
                    "replicate_id": suffix,
                    "pair_id": biological_sample,
                    "input_ng": input_ng,
                    "dv200": dv200,
                    "sequencing_run": (f"run-{input_ng}" if confounded else f"run-{sample_index}"),
                    "operator": f"operator-{sample_index}",
                    "reagent_lot": "lot-1" if sample_index == 1 else "lot-2",
                    "instrument": "instrument-1",
                    "processing_order": len(rows) + 1,
                }
            )
    return rows


async def _base_guided_workspace(client: AsyncClient) -> tuple[str, str]:
    project_response = await client.post(
        "/api/projects",
        json={"name": "Synthetic FFPE experiment", "description": "G2 test"},
    )
    project_id = project_response.json()["id"]
    assay_response = await client.post(
        "/api/assay-projects",
        json={
            "project_id": project_id,
            "name": "FFPE input development",
            "proposed_purpose": "Explore stable RNA input for a research endpoint.",
            "specimen_type": "simulated_ffpe_tumor",
            "biological_context": "Synthetic tumor RNA measurements.",
            "proposed_output": "expression_classifier_score",
            "current_stage": "FEASIBILITY",
            "assay_version": "development-unlocked",
        },
    )
    assay_id = assay_response.json()["id"]
    question_response = await client.post(
        f"/api/assay-projects/{assay_id}/questions",
        json={
            "question_key": "input_degradation_stability",
            "formal_question": "Whether 25 ng remains a candidate development condition.",
            "source": "USER_SELECTED",
        },
    )
    return project_id, question_response.json()["id"]


async def _prepared_bundle_record(
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    project_id: str,
) -> None:
    bundle_buffer = BytesIO()
    metadata = (
        "sample_id\tbiological_sample_id\tinput_ng\tdv200\tsequencing_run\toperator\n"
        + "\n".join(
            f"{row['measurement_id']}\t{row['biological_sample_id']}\t{row['input_ng']}\t"
            f"{row['dv200']}\t{row['sequencing_run']}\t{row['operator']}"
            for row in _assignments(confounded=False)
        )
        + "\n"
    ).encode()
    bundle_manifest = json.dumps({"sample_metadata": "sample_metadata.tsv"}).encode()
    with tarfile.open(fileobj=bundle_buffer, mode="w:gz") as archive:
        for name, source in (
            ("expression_bundle/bundle_manifest.json", bundle_manifest),
            ("expression_bundle/sample_metadata.tsv", metadata),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(source)
            archive.addfile(info, BytesIO(source))
    bundle = storage.put(
        ("tests", "experiments"),
        "expression_bundle.tar.gz",
        BytesIO(bundle_buffer.getvalue()),
    )
    manifest = storage.put(("tests", "experiments"), "bundle_manifest.json", BytesIO(b"{}"))
    async with session_factory() as session:
        dataset = Dataset(
            id="dataset-ffpe",
            project_id=project_id,
            name="Synthetic FFPE expression",
            modality="bulk_rnaseq",
            source_kind="count_matrix",
            organism="Homo sapiens",
            genome_build="GRCh38",
            annotation_release="GENCODE 49",
            status="prepared",
        )
        preparation = Run(
            id="preparation-run",
            run_type="dataset_preparation",
            dataset_id=dataset.id,
            state="SUCCEEDED",
            profile="test",
            params_uri="local://params",
            output_uri="run://preparation-run/output",
            work_uri="run://preparation-run/work",
        )
        prepared = PreparedDataset(
            id="prepared-ffpe",
            dataset_id=dataset.id,
            version=1,
            preparation_run_id=preparation.id,
            bundle_uri=bundle.uri,
            bundle_manifest_uri=manifest.uri,
            value_types_available=["log_expression"],
            sample_count=6,
            feature_count=12,
            qc_status="PASS",
        )
        session.add_all([dataset, preparation, prepared])
        await session.flush()
        session.add(
            Artifact(
                run_id=preparation.id,
                artifact_type="expression_bundle",
                title="Expression Bundle",
                relative_path="expression_bundle.tar.gz",
                storage_uri=bundle.uri,
                mime_type="application/gzip",
                size_bytes=bundle.size_bytes,
                sha256=bundle.sha256,
                display_order=1,
                metadata_json={},
            )
        )
        await session.commit()


async def _multifactor_bundle_record(
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    project_id: str,
    tmp_path: Path,
) -> list[dict[str, object]]:
    generated = generate_multifactor(tmp_path / "multifactor-inputs")
    bundle = storage.put(
        ("tests", "multifactor"),
        "expression_bundle.tar.gz",
        BytesIO(Path(generated["expression_bundle"]).read_bytes()),
    )
    manifest = storage.put(("tests", "multifactor"), "bundle_manifest.json", BytesIO(b"{}"))
    with Path(generated["experiment_assignments"]).open(newline="") as source:
        import csv

        raw = list(csv.DictReader(source, delimiter="\t"))
    assignments: list[dict[str, object]] = []
    for row in raw:
        assignments.append(
            {
                **row,
                "prepared_dataset_id": "prepared-multifactor",
                "include": True,
                "exclusion_reason": None,
                "input_ng": float(row["input_ng"]),
                "processing_order": int(row["processing_order"]),
            }
        )
    async with session_factory() as session:
        dataset = Dataset(
            id="dataset-multifactor",
            project_id=project_id,
            name="Balanced multifactor expression",
            modality="bulk_rnaseq",
            source_kind="count_matrix",
            organism="Homo sapiens",
            status="prepared",
        )
        run = Run(
            id="preparation-run-multifactor",
            run_type="dataset_preparation",
            dataset_id=dataset.id,
            state="SUCCEEDED",
            profile="test",
            params_uri="local://multifactor-params",
            output_uri="run://multifactor/output",
            work_uri="run://multifactor/work",
        )
        prepared = PreparedDataset(
            id="prepared-multifactor",
            dataset_id=dataset.id,
            version=1,
            preparation_run_id=run.id,
            bundle_uri=bundle.uri,
            bundle_manifest_uri=manifest.uri,
            value_types_available=["log_expression"],
            sample_count=24,
            feature_count=20,
            qc_status="PASS",
        )
        session.add_all([dataset, run, prepared])
        await session.flush()
        session.add(
            Artifact(
                run_id=run.id,
                artifact_type="expression_bundle",
                title="Expression Bundle",
                relative_path="expression_bundle.tar.gz",
                storage_uri=bundle.uri,
                mime_type="application/gzip",
                size_bytes=bundle.size_bytes,
                sha256=bundle.sha256,
                display_order=1,
                metadata_json={},
            )
        )
        await session.commit()
    return assignments


async def test_experiment_design_repair_lock_clone_export_and_queue(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    dispatched_experiment_ids: list[str],
) -> None:
    project_id, question_id = await _base_guided_workspace(client)
    await _prepared_bundle_record(session_factory, storage, project_id)
    assay = (await client.get(f"/api/projects/{project_id}/assay-development")).json()
    input_options = await client.get(f"/api/assay-projects/{assay['id']}/experiment-input-options")
    assert input_options.status_code == 200
    assert input_options.json()[0]["prepared_dataset_id"] == "prepared-ffpe"
    design_options = await client.get(
        "/api/prepared-datasets/prepared-ffpe/experiment-design-options"
    )
    assert design_options.status_code == 200
    assert design_options.json()["measurement_ids"] == [
        row["measurement_id"] for row in _assignments(confounded=False)
    ]
    assert "biological_sample_id" in design_options.json()["metadata_columns"]
    create_payload = {
        "assay_project_id": assay["id"],
        "question_id": question_id,
        "prepared_dataset_id": "prepared-ffpe",
        "name": "FFPE RNA input feasibility",
        "objective": "Explore paired profile stability across RNA input and DV200.",
        "experiment_type": "INPUT_DEGRADATION_EXPLORATION",
        "mode": "ANALYZE_EXISTING",
        "reference_level": 100,
        "assay": "log_expression",
        "declared_questions": ["Is profile correlation stable through 25 ng?"],
        "reference_level_rationale": "Highest routinely available input condition.",
        "endpoint_rationale": "Profile stability is required before classifier development.",
        "assignments": _assignments(confounded=True),
    }
    created = await client.post("/api/experiments", json=create_payload)
    assert created.status_code == 201
    experiment = created.json()
    assert experiment["status"] == "DESIGN_INVALID"
    errors = {item["code"] for item in experiment["design_validation"]["errors"]}
    assert "DESIGN.INPUT_RUN_CONFOUNDED" in errors

    blocked_lock = await client.post(f"/api/experiments/{experiment['id']}/lock-execution-revision")
    assert blocked_lock.status_code == 409

    repaired = await client.patch(
        f"/api/experiments/{experiment['id']}",
        json={"assignments": _assignments(confounded=False)},
    )
    assert repaired.status_code == 200
    assert repaired.json()["status"] == "DESIGN_VALID"
    assert repaired.json()["design_validation"]["valid"] is True
    assert any(
        item["code"] == "DESIGN.RETROSPECTIVE_MAPPING"
        for item in repaired.json()["design_validation"]["warnings"]
    )

    wet_lab = await client.get(f"/api/experiments/{experiment['id']}/wet-lab-package")
    assert wet_lab.status_code == 200
    with ZipFile(BytesIO(wet_lab.content)) as package:
        assert {
            "experiment_spec.json",
            "sample_assignment.tsv",
            "randomization_schedule.csv",
            "required_metadata_template.csv",
            "protocol_variable_checklist.md",
            "acceptance_or_learning_questions.md",
            "readme.md",
        } <= set(package.namelist())
        assert b"does not replace an approved laboratory protocol" in package.read("readme.md")

    locked = await client.post(f"/api/experiments/{experiment['id']}/lock-execution-revision")
    assert locked.status_code == 200
    locked_payload = locked.json()
    assert locked_payload["status"] == "LOCKED_FOR_EXECUTION"
    assert len(locked_payload["experiment_spec_sha256"]) == 64
    assert len(locked_payload["assignments_sha256"]) == 64

    immutable = await client.patch(
        f"/api/experiments/{experiment['id']}", json={"name": "Forbidden change"}
    )
    assert immutable.status_code == 409
    assert "clone" in immutable.json()["detail"].lower()

    clone = await client.post(f"/api/experiments/{experiment['id']}/clone")
    assert clone.status_code == 201
    assert clone.json()["parent_experiment_id"] == experiment["id"]
    assert clone.json()["experiment_spec_sha256"] is None

    async with session_factory() as session:
        follow_up_recommendation = Recommendation(
            assay_project_id=assay["id"],
            source_type="EXPERIMENT",
            source_id=experiment["id"],
            rule_id="INPUT_DEGRADATION.BALANCED_CONFIRMATION",
            recommendation_type="CREATE_EXPERIMENT",
            title="Review a balanced confirmation experiment",
            summary="Create a prospectively balanced draft.",
            why="Exploratory behavior needs confirmation.",
            what_it_resolves="Whether behavior persists in a balanced design.",
            stage="FEASIBILITY",
            priority=70,
            requirement_level="RECOMMENDED",
            status="OPEN",
            required_inputs_json=["balanced assignment plan"],
            expected_output="An editable follow-up draft.",
            proposed_action_json={"experiment_type": "INPUT_DEGRADATION_EXPLORATION"},
            evidence_refs_json=[{"path": "results/primary_results.json"}],
            assumptions_json=[],
            limitations_json=[],
            alternative_action_ids_json=[],
        )
        session.add(follow_up_recommendation)
        await session.commit()
        recommendation_id = follow_up_recommendation.id
    follow_up = await client.post(
        f"/api/experiments/{experiment['id']}/recommendations/{recommendation_id}/accept-follow-up",
        json={"rationale": "A balanced confirmation is the appropriate next learning step."},
    )
    assert follow_up.status_code == 201
    assert follow_up.json()["parent_experiment_id"] == experiment["id"]
    assert follow_up.json()["mode"] == "PLAN_FIRST"
    assert follow_up.json()["status"] == "DESIGN_VALID"

    queued = await client.post(f"/api/experiments/{experiment['id']}/run")
    assert queued.status_code == 202
    queued_payload = queued.json()
    assert queued_payload["run_state"] == "QUEUED"
    assert queued_payload["experiment"]["status"] == "QUEUED"
    assert dispatched_experiment_ids == [queued_payload["run_id"]]

    results = await client.get(f"/api/experiments/{experiment['id']}/results")
    assert results.status_code == 200
    assert results.json()["status"] == "QUEUED"
    assert results.json()["decision_summary"] is None

    cancelled = await client.post(f"/api/runs/{queued_payload['run_id']}/cancel")
    assert cancelled.status_code == 202
    assert cancelled.json()["state"] == "CANCELLED"
    cancelled_experiment = await client.get(f"/api/experiments/{experiment['id']}")
    assert cancelled_experiment.json()["status"] == "CANCELLED"


def _paired_assignments(*, confounded: bool = False) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sample_index in range(1, 5):
        for condition in ("method_a", "method_b"):
            rows.append(
                {
                    "measurement_id": f"pair_{sample_index}_{condition}",
                    "biological_sample_id": f"pair_{sample_index}",
                    "prepared_dataset_id": "prepared-paired",
                    "include": True,
                    "replicate_id": condition,
                    "pair_id": f"pair_{sample_index}",
                    "condition": condition,
                    "run": f"run_{condition}" if confounded else f"run_{1 + sample_index % 2}",
                    "operator": f"operator_{1 + sample_index % 2}",
                    "reagent_lot": f"lot_{1 + sample_index % 2}",
                    "quality_metric": 40 + sample_index * 10,
                    "processing_order": len(rows) + 1,
                }
            )
    return rows


async def _paired_workspace(client: AsyncClient) -> tuple[str, str, str]:
    project = (
        await client.post(
            "/api/projects",
            json={"name": "Paired condition project", "description": "G6 API test"},
        )
    ).json()
    assay = (
        await client.post(
            "/api/assay-projects",
            json={
                "project_id": project["id"],
                "name": "Library optimization",
                "proposed_purpose": "Compare paired library conditions.",
                "specimen_type": "simulated_ffpe_tumor",
                "biological_context": "Paired technical measurements.",
                "proposed_output": "expression_endpoint",
                "current_stage": "OPTIMIZE",
                "assay_version": "development-unlocked",
            },
        )
    ).json()
    question = (
        await client.post(
            f"/api/assay-projects/{assay['id']}/questions",
            json={
                "question_key": "paired_condition_performance",
                "formal_question": "Whether either method merits confirmation.",
                "source": "USER_SELECTED",
            },
        )
    ).json()
    return project["id"], assay["id"], question["id"]


async def _paired_prepared_record(
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    project_id: str,
) -> None:
    rows = _paired_assignments()
    metadata = (
        "sample_id\tbiological_sample_id\tmethod\trun\toperator\treagent_lot\tquality_metric\n"
        + "\n".join(
            f"{row['measurement_id']}\t{row['biological_sample_id']}\t{row['condition']}\t"
            f"{row['run']}\t{row['operator']}\t{row['reagent_lot']}\t{row['quality_metric']}"
            for row in rows
        )
        + "\n"
    ).encode()
    archive_buffer = BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w:gz") as archive:
        for name, source in (
            (
                "expression_bundle/bundle_manifest.json",
                json.dumps({"sample_metadata": "sample_metadata.tsv"}).encode(),
            ),
            ("expression_bundle/sample_metadata.tsv", metadata),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(source)
            archive.addfile(info, BytesIO(source))
    bundle = storage.put(
        ("tests", "paired-experiment"),
        "expression_bundle.tar.gz",
        BytesIO(archive_buffer.getvalue()),
    )
    manifest = storage.put(("tests", "paired-experiment"), "bundle_manifest.json", BytesIO(b"{}"))
    async with session_factory() as session:
        dataset = Dataset(
            id="dataset-paired",
            project_id=project_id,
            name="Paired method expression",
            modality="bulk_rnaseq",
            source_kind="count_matrix",
            organism="Homo sapiens",
            genome_build="GRCh38",
            annotation_release="GENCODE 49",
            status="prepared",
        )
        preparation = Run(
            id="paired-preparation-run",
            run_type="dataset_preparation",
            dataset_id=dataset.id,
            state="SUCCEEDED",
            profile="test",
            params_uri="local://params",
            output_uri="run://paired-preparation/output",
            work_uri="run://paired-preparation/work",
        )
        prepared = PreparedDataset(
            id="prepared-paired",
            dataset_id=dataset.id,
            version=1,
            preparation_run_id=preparation.id,
            bundle_uri=bundle.uri,
            bundle_manifest_uri=manifest.uri,
            value_types_available=["log_expression"],
            sample_count=len(rows),
            feature_count=16,
            qc_status="PASS",
        )
        session.add_all([dataset, preparation, prepared])
        await session.flush()
        session.add(
            Artifact(
                run_id=preparation.id,
                artifact_type="expression_bundle",
                title="Expression Bundle",
                relative_path="expression_bundle.tar.gz",
                storage_uri=bundle.uri,
                mime_type="application/gzip",
                size_bytes=bundle.size_bytes,
                sha256=bundle.sha256,
                display_order=1,
                metadata_json={},
            )
        )
        await session.commit()


async def test_paired_condition_experiment_lifecycle_and_queue(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    dispatched_experiment_ids: list[str],
) -> None:
    project_id, assay_id, question_id = await _paired_workspace(client)
    await _paired_prepared_record(session_factory, storage, project_id)
    options = await client.get("/api/prepared-datasets/prepared-paired/experiment-design-options")
    assert options.status_code == 200
    assert {"method", "run", "quality_metric"} <= set(options.json()["metadata_columns"])
    payload = {
        "assay_project_id": assay_id,
        "question_id": question_id,
        "prepared_dataset_id": "prepared-paired",
        "name": "Paired library method comparison",
        "objective": "Compare paired expression endpoints across methods.",
        "experiment_type": "PAIRED_CONDITION_COMPARISON",
        "mode": "ANALYZE_EXISTING",
        "reference_condition": "method_a",
        "comparator_condition": "method_b",
        "assay": "log_expression",
        "primary_endpoints": [
            "paired_mean_expression_difference",
            "expression_profile_correlation",
        ],
        "secondary_endpoints": ["failure_rate", "per_sample_discordance"],
        "declared_questions": ["Do the complementary endpoints favor confirmation?"],
        "condition_contrast_rationale": "Method A is the current process reference.",
        "endpoint_rationale": "Bias, concordance, failures, and discordance are complementary.",
        "assignments": _paired_assignments(confounded=True),
    }
    created = await client.post("/api/experiments", json=payload)
    assert created.status_code == 201
    assert created.json()["status"] == "DESIGN_INVALID"
    assert "DESIGN.CONDITION_RUN_CONFOUNDED" in {
        item["code"] for item in created.json()["design_validation"]["errors"]
    }
    repaired = await client.patch(
        f"/api/experiments/{created.json()['id']}",
        json={"assignments": _paired_assignments()},
    )
    assert repaired.status_code == 200
    assert repaired.json()["design_validation"]["complete_pair_count"] == 4
    locked = await client.post(f"/api/experiments/{created.json()['id']}/lock-execution-revision")
    assert locked.status_code == 200
    assert locked.json()["experiment_spec"]["analysis_plan"]["template"] == (
        "paired_condition_multi_endpoint_comparison"
    )
    queued = await client.post(f"/api/experiments/{created.json()['id']}/run")
    assert queued.status_code == 202
    assert queued.json()["run_state"] == "QUEUED"
    assert dispatched_experiment_ids == [queued.json()["run_id"]]


async def test_technical_feasibility_experiment_design_lock_and_queue(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    dispatched_experiment_ids: list[str],
) -> None:
    project_id, _ = await _base_guided_workspace(client)
    await _prepared_bundle_record(session_factory, storage, project_id)
    assay = (await client.get(f"/api/projects/{project_id}/assay-development")).json()
    question = (
        await client.post(
            f"/api/assay-projects/{assay['id']}/questions",
            json={
                "question_key": "usable_rna_feasibility",
                "formal_question": "Whether tested specimens produce usable measurements.",
                "source": "USER_SELECTED",
            },
        )
    ).json()
    technical_assignments = [
        {
            **row,
            "run": row["sequencing_run"],
            "specimen_group": "FFPE",
            "technical_failure": index == 1,
        }
        for index, row in enumerate(_assignments(confounded=False))
    ]
    created = await client.post(
        "/api/experiments",
        json={
            "assay_project_id": assay["id"],
            "question_id": question["id"],
            "prepared_dataset_id": "prepared-ffpe",
            "name": "Usable RNA technical feasibility",
            "objective": "Summarize explicit technical success and failure patterns.",
            "experiment_type": "TECHNICAL_FEASIBILITY",
            "mode": "ANALYZE_EXISTING",
            "assay": "log_expression",
            "primary_endpoints": ["technical_success_rate", "detected_genes"],
            "secondary_endpoints": ["input_ng", "dv200", "failure_association_review"],
            "declared_questions": ["Do the tested conditions merit further development?"],
            "condition_contrast_rationale": "Review tested specimens descriptively.",
            "endpoint_rationale": "Success and expression suitability are complementary.",
            "assignments": technical_assignments,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "DESIGN_VALID"
    assert created.json()["design_validation"]["specimen_groups"] == ["FFPE"]
    locked = await client.post(f"/api/experiments/{created.json()['id']}/lock-execution-revision")
    assert locked.status_code == 200
    assert locked.json()["experiment_spec"]["analysis_plan"]["template"] == (
        "technical_feasibility_summary"
    )
    queued = await client.post(f"/api/experiments/{created.json()['id']}/run")
    assert queued.status_code == 202
    assert dispatched_experiment_ids == [queued.json()["run_id"]]


async def test_multifactor_experiment_design_lock_and_queue(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    dispatched_experiment_ids: list[str],
    tmp_path: Path,
) -> None:
    project = (
        await client.post(
            "/api/projects",
            json={"name": "Multifactor optimization", "description": "G6 API test"},
        )
    ).json()
    assay = (
        await client.post(
            "/api/assay-projects",
            json={
                "project_id": project["id"],
                "name": "Method and input optimization",
                "proposed_purpose": "Select conditions for confirmation.",
                "specimen_type": "synthetic expression",
                "biological_context": "Balanced repeated-sample factorial design.",
                "proposed_output": "expression endpoint",
                "current_stage": "OPTIMIZE",
                "assay_version": "development-unlocked",
            },
        )
    ).json()
    question = (
        await client.post(
            f"/api/assay-projects/{assay['id']}/questions",
            json={
                "question_key": "multifactor_optimization",
                "formal_question": "Which method and input combinations merit confirmation?",
                "source": "USER_SELECTED",
            },
        )
    ).json()
    assignments = await _multifactor_bundle_record(
        session_factory, storage, project["id"], tmp_path
    )
    created = await client.post(
        "/api/experiments",
        json={
            "assay_project_id": assay["id"],
            "question_id": question["id"],
            "prepared_dataset_id": "prepared-multifactor",
            "name": "Constrained method by input optimization",
            "objective": "Estimate bounded fixed effects and one interaction.",
            "experiment_type": "MULTIFACTOR_OPTIMIZATION",
            "mode": "ANALYZE_EXISTING",
            "assay": "log_expression",
            "primary_endpoints": ["mean_expression", "fixed_effect_estimates"],
            "secondary_endpoints": ["variance_decomposition"],
            "declared_questions": ["Which cells merit confirmation?"],
            "condition_contrast_rationale": (
                "Extraction method and input are controllable primary factors."
            ),
            "endpoint_rationale": "Fixed effects and variance are complementary.",
            "factor_names": ["extraction_method", "input_ng"],
            "interactions": ["extraction_method:input_ng"],
            "assignments": assignments,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "DESIGN_VALID"
    assert created.json()["design_validation"]["residual_degrees_of_freedom"] >= 3
    locked = await client.post(f"/api/experiments/{created.json()['id']}/lock-execution-revision")
    assert locked.status_code == 200
    assert locked.json()["experiment_spec"]["analysis_plan"]["factor_names"] == [
        "extraction_method",
        "input_ng",
    ]
    queued = await client.post(f"/api/experiments/{created.json()['id']}/run")
    assert queued.status_code == 202
    assert dispatched_experiment_ids == [queued.json()["run_id"]]
