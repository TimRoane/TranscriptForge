"""API lifecycle coverage for the precision/reproducibility validation slice."""

import io
import json
import tarfile
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from transcriptforge_api.models import (
    Analysis,
    Artifact,
    Dataset,
    ModelRecord,
    PreparedDataset,
    Run,
)
from transcriptforge_api.models.base import new_id
from transcriptforge_api.storage.local import LocalStorage

from apps.api.tests.test_model_lifecycle import _candidate
from demo.assay_development.generate_input_limit_fixture import generate as generate_limit
from demo.assay_development.generate_paired_bridge_fixture import generate as generate_bridge
from demo.assay_development.generate_robustness_fixture import generate as generate_robustness


def _assignments(*, constant_run: bool = False) -> list[dict[str, object]]:
    rows = []
    for sample in range(1, 5):
        for repeat in (1, 2):
            rows.append(
                {
                    "measurement_id": f"bio_{sample}_{repeat}",
                    "biological_sample_id": f"bio_{sample}",
                    "replicate_id": str(repeat),
                    "operator": f"operator_{repeat}",
                    "run": "run_1" if constant_run else f"run_{(sample - 1) % 2 + 1}",
                    "reagent_lot": f"lot_{repeat}",
                    "instrument": "instrument_1",
                    "day": f"day_{(sample - 1) % 2 + 1}",
                    "site": "site_1",
                    "include": True,
                    "exclusion_reason": None,
                }
            )
    return rows


async def _validation_bundle(
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    project_id: str,
) -> str:
    sample_ids = [row["measurement_id"] for row in _assignments()]
    values = [-2.05, -1.95, -1.05, -0.95, 2.95, 3.05, 3.95, 4.05]
    manifest = {
        "assays": [{"name": "log_expression", "path": "assays/log_expression.tsv"}],
        "sample_metadata": "metadata/sample_metadata.tsv",
    }
    assay = (
        "feature_id\t"
        + "\t".join(str(item) for item in sample_ids)
        + "\nG1\t"
        + "\t".join(str(value) for value in values)
        + "\nG2\t"
        + "\t".join("2" for _ in values)
        + "\n"
    ).encode()
    metadata = (
        "sample_id\tbiological_sample_id\treplicate_id\toperator\trun\treagent_lot\n"
        + "\n".join(
            f"{row['measurement_id']}\t{row['biological_sample_id']}\t{row['replicate_id']}\t"
            f"{row['operator']}\t{row['run']}\t{row['reagent_lot']}"
            for row in _assignments()
        )
        + "\n"
    ).encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in (
            ("expression_bundle/bundle_manifest.json", json.dumps(manifest).encode()),
            ("expression_bundle/assays/log_expression.tsv", assay),
            ("expression_bundle/metadata/sample_metadata.tsv", metadata),
        ):
            member = tarfile.TarInfo(name)
            member.size = len(content)
            member.mtime = 0
            archive.addfile(member, io.BytesIO(content))
    stored_bundle = storage.put(
        ("tests", "studies"), "validation_expression_bundle.tar.gz", io.BytesIO(buffer.getvalue())
    )
    stored_manifest = storage.put(
        ("tests", "studies"), "bundle_manifest.json", io.BytesIO(json.dumps(manifest).encode())
    )
    dataset_id, prepared_id, run_id = new_id(), new_id(), new_id()
    async with session_factory() as session:
        session.add(
            Dataset(
                id=dataset_id,
                project_id=project_id,
                name="Repeated-measure validation cohort",
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
                params_uri="test://validation-preparation",
                output_uri="test://validation-output",
                work_uri="test://validation-work",
            )
        )
        await session.flush()
        session.add(
            PreparedDataset(
                id=prepared_id,
                dataset_id=dataset_id,
                version=1,
                preparation_run_id=run_id,
                bundle_uri=stored_bundle.uri,
                bundle_manifest_uri=stored_manifest.uri,
                value_types_available=["log_expression"],
                sample_count=len(sample_ids),
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
                storage_uri=stored_bundle.uri,
                mime_type="application/gzip",
                size_bytes=stored_bundle.size_bytes,
                sha256=stored_bundle.sha256,
                display_order=1,
                metadata_json={},
            )
        )
        await session.commit()
    return prepared_id


async def test_precision_study_design_lock_queue_immutability_and_cancel(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    dispatched_study_ids: list[str],
) -> None:
    model_id = await _candidate(session_factory, storage)
    assert (
        await client.post(f"/api/models/{model_id}/review", json={"rationale": "review"})
    ).status_code == 200
    assert (
        await client.post(f"/api/models/{model_id}/lock", json={"rationale": "lock"})
    ).status_code == 200
    async with session_factory() as session:
        model = await session.get(ModelRecord, model_id)
        assert model is not None
        analysis = await session.get(Analysis, model.analysis_id)
        assert analysis is not None
        project_id = analysis.project_id
    assay_response = await client.post(
        "/api/assay-projects",
        json={
            "project_id": project_id,
            "name": "Locked classifier validation",
            "proposed_purpose": "Research-only precision evaluation.",
            "specimen_type": "synthetic repeated expression",
            "biological_context": "Synthetic model validation.",
            "proposed_output": "locked classifier score and call",
            "current_stage": "VALIDATE",
            "assay_version": "demo-1.0",
        },
    )
    assert assay_response.status_code == 201
    assay_id = assay_response.json()["id"]
    question_response = await client.post(
        f"/api/assay-projects/{assay_id}/questions",
        json={
            "question_key": "precision_reproducibility",
            "formal_question": "Is the locked score repeatable across operators and runs?",
            "source": "USER_SELECTED",
        },
    )
    assert question_response.status_code == 201
    question_id = question_response.json()["id"]
    prepared_id = await _validation_bundle(session_factory, storage, project_id)

    options = await client.get(f"/api/assay-projects/{assay_id}/study-input-options")
    assert options.status_code == 200
    assert {item["id"] for item in options.json()["locked_models"]} == {model_id}
    assert prepared_id in {item["id"] for item in options.json()["prepared_datasets"]}

    payload = {
        "assay_project_id": assay_id,
        "question_id": question_id,
        "model_id": model_id,
        "prepared_dataset_id": prepared_id,
        "name": "Classifier precision and reproducibility",
        "objective": "Quantify repeatability without changing or retraining the locked model.",
        "study_type": "PRECISION_REPRODUCIBILITY",
        "assignments": _assignments(constant_run=True),
        "factors": ["operator", "run"],
        "criteria": [
            {
                "key": "score_icc",
                "metric": "icc",
                "endpoint": "classifier_score",
                "operator": "gte",
                "threshold": 0.9,
                "rationale": "Prespecified research demonstration threshold.",
            },
            {
                "key": "call_agreement",
                "metric": "categorical_agreement",
                "endpoint": "predicted_class",
                "operator": "gte",
                "threshold": 0.95,
                "rationale": "Prespecified research demonstration threshold.",
            },
        ],
        "bootstrap_iterations": 200,
    }
    created = await client.post("/api/studies", json=payload)
    assert created.status_code == 201, created.text
    study = created.json()
    assert study["status"] == "DESIGN_INVALID"
    assert "STUDY.FACTOR_LEVELS_INSUFFICIENT" in {
        item["code"] for item in study["design_validation_json"]["errors"]
    }
    assert (await client.post(f"/api/studies/{study['id']}/lock")).status_code == 409

    repaired = await client.patch(
        f"/api/studies/{study['id']}", json={"assignments": _assignments()}
    )
    assert repaired.status_code == 200, repaired.text
    assert repaired.json()["status"] == "DESIGN_VALID"
    locked = await client.post(f"/api/studies/{study['id']}/lock")
    assert locked.status_code == 200, locked.text
    assert locked.json()["status"] == "LOCKED"
    assert len(locked.json()["study_spec_sha256"]) == 64
    assert len(locked.json()["assignments_sha256"]) == 64

    immutable = await client.patch(f"/api/studies/{study['id']}", json={"name": "changed"})
    assert immutable.status_code == 409
    clone = await client.post(f"/api/studies/{study['id']}/clone")
    assert clone.status_code == 201
    assert clone.json()["parent_study_id"] == study["id"]

    queued = await client.post(f"/api/studies/{study['id']}/run")
    assert queued.status_code == 202, queued.text
    run_id = queued.json()["run_id"]
    assert dispatched_study_ids == [run_id]
    cancelled = await client.post(f"/api/runs/{run_id}/cancel")
    assert cancelled.status_code == 202
    assert cancelled.json()["state"] == "CANCELLED"
    assert (await client.get(f"/api/studies/{study['id']}")).json()["status"] == "CANCELLED"


def _limit_assignments(*, incomplete: bool = False) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sample in range(1, 5):
        for level in (100, 50, 25):
            rows.append(
                {
                    "measurement_id": f"limit_{sample}_{level}",
                    "biological_sample_id": f"limit_{sample}",
                    "replicate_id": str(level),
                    "operator": f"operator_{1 + sample % 2}",
                    "run": f"run_{1 + sample % 2}",
                    "reagent_lot": f"lot_{1 + sample % 2}",
                    "input_level": level,
                    "quality_metric": 40 + level / 2 + sample,
                    "qc_failure": False,
                    "include": True,
                    "exclusion_reason": None,
                }
            )
    return rows[:-1] if incomplete else rows


async def _input_limit_bundle(
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    project_id: str,
    fixture_dir: Path,
    *,
    paired_bridge: bool = False,
    robustness: bool = False,
) -> str:
    generator = (
        generate_robustness if robustness else generate_bridge if paired_bridge else generate_limit
    )
    generated = generator(fixture_dir)
    bundle_bytes = Path(generated["expression_bundle"]).read_bytes()
    stored_bundle = storage.put(
        ("tests", "input-limit"), "expression_bundle.tar.gz", io.BytesIO(bundle_bytes)
    )
    stored_manifest = storage.put(
        ("tests", "input-limit"), "bundle_manifest.json", io.BytesIO(b"{}")
    )
    dataset_id, prepared_id, run_id = new_id(), new_id(), new_id()
    async with session_factory() as session:
        dataset = Dataset(
            id=dataset_id,
            project_id=project_id,
            name=(
                "Paired bridge validation cohort"
                if paired_bridge or robustness
                else "Input-limit validation cohort"
            ),
            modality="bulk_rnaseq",
            source_kind="count_matrix",
            organism="Homo sapiens",
            status="prepared",
        )
        preparation = Run(
            id=run_id,
            run_type="dataset_preparation",
            dataset_id=dataset_id,
            state="SUCCEEDED",
            profile="test",
            params_uri="test://input-limit-preparation",
            output_uri="test://input-limit-output",
            work_uri="test://input-limit-work",
        )
        prepared = PreparedDataset(
            id=prepared_id,
            dataset_id=dataset_id,
            version=1,
            preparation_run_id=run_id,
            bundle_uri=stored_bundle.uri,
            bundle_manifest_uri=stored_manifest.uri,
            value_types_available=["log_expression"],
            sample_count=12,
            feature_count=2,
            qc_status="PASS",
        )
        session.add_all([dataset, preparation, prepared])
        await session.flush()
        session.add(
            Artifact(
                run_id=run_id,
                artifact_type="expression_bundle",
                title="Expression Bundle",
                relative_path="expression_bundle.tar.gz",
                storage_uri=stored_bundle.uri,
                mime_type="application/gzip",
                size_bytes=stored_bundle.size_bytes,
                sha256=stored_bundle.sha256,
                display_order=1,
                metadata_json={},
            )
        )
        await session.commit()
    return prepared_id


async def test_input_degradation_limit_study_design_lock_and_queue(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    dispatched_study_ids: list[str],
    tmp_path: Path,
) -> None:
    model_id = await _candidate(session_factory, storage)
    assert (
        await client.post(f"/api/models/{model_id}/review", json={"rationale": "review"})
    ).status_code == 200
    assert (
        await client.post(f"/api/models/{model_id}/lock", json={"rationale": "lock"})
    ).status_code == 200
    async with session_factory() as session:
        model = await session.get(ModelRecord, model_id)
        assert model is not None
        analysis = await session.get(Analysis, model.analysis_id)
        assert analysis is not None
        project_id = analysis.project_id
    assay = (
        await client.post(
            "/api/assay-projects",
            json={
                "project_id": project_id,
                "name": "Locked endpoint input validation",
                "proposed_purpose": "Research-only input-limit evaluation.",
                "specimen_type": "synthetic paired expression",
                "biological_context": "Synthetic locked endpoint validation.",
                "proposed_output": "locked classifier score and call",
                "current_stage": "VALIDATE",
                "assay_version": "demo-1.0",
            },
        )
    ).json()
    question = (
        await client.post(
            f"/api/assay-projects/{assay['id']}/questions",
            json={
                "question_key": "input_degradation_limit_validation",
                "formal_question": "What lowest tested level meets the declared criteria?",
                "source": "USER_SELECTED",
            },
        )
    ).json()
    prepared_id = await _input_limit_bundle(
        session_factory, storage, project_id, tmp_path / "limit-fixture"
    )
    payload = {
        "assay_project_id": assay["id"],
        "question_id": question["id"],
        "model_id": model_id,
        "prepared_dataset_id": prepared_id,
        "name": "Locked endpoint input limit",
        "objective": "Evaluate paired ordered levels without retraining.",
        "study_type": "INPUT_DEGRADATION_LIMIT",
        "assignments": _limit_assignments(incomplete=True),
        "factors": ["input_level", "run"],
        "reference_level": 100,
        "level_rationale": "The highest tested level is the reference.",
        "criteria": [
            {
                "key": "score_stability_all_levels",
                "metric": "mean_absolute_score_difference",
                "endpoint": "classifier_score",
                "operator": "all_levels",
                "threshold": 0.1,
                "rationale": "Maximum score change at every lower level.",
            },
            {
                "key": "call_stability_consecutive",
                "metric": "call_agreement_to_reference",
                "endpoint": "predicted_class",
                "operator": "consecutive_levels",
                "threshold": 0.95,
                "rationale": "Call agreement through consecutive levels.",
            },
        ],
        "bootstrap_iterations": 200,
    }
    rejected = await client.post("/api/studies", json=payload)
    assert rejected.status_code == 409
    assert "map every immutable bundle sample" in rejected.json()["detail"]
    payload["assignments"] = _limit_assignments()
    created = await client.post("/api/studies", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "DESIGN_VALID"
    assert created.json()["design_validation_json"]["ordered_levels"] == [100, 50, 25]
    locked = await client.post(f"/api/studies/{created.json()['id']}/lock")
    assert locked.status_code == 200
    assert locked.json()["study_spec_json"]["analysis_plan"]["template"] == (
        "ordered_level_locked_endpoint_limit"
    )
    queued = await client.post(f"/api/studies/{created.json()['id']}/run")
    assert queued.status_code == 202
    assert dispatched_study_ids == [queued.json()["run_id"]]


def _bridge_assignments(
    *, confounded: bool = False, robustness: bool = False
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sample in range(1, 7):
        for condition in ("pipeline_a", "pipeline_b"):
            rows.append(
                {
                    "measurement_id": f"bridge_{sample}_{condition}",
                    "biological_sample_id": f"bridge_{sample}",
                    "replicate_id": condition,
                    "operator": f"operator_{1 + sample % 2}",
                    "run": f"run_{condition}" if confounded else f"run_{1 + sample % 2}",
                    "reagent_lot": f"lot_{1 + sample % 2}",
                    "condition": condition,
                    "challenge_type": "hemoglobin" if robustness else None,
                    "qc_failure": False,
                    "subgroup": "low_quality" if sample <= 3 else "high_quality",
                    "include": True,
                    "exclusion_reason": None,
                }
            )
    return rows


async def test_paired_bridging_requires_bias_criterion_and_queues_valid_design(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    dispatched_study_ids: list[str],
    tmp_path: Path,
) -> None:
    model_id = await _candidate(session_factory, storage)
    await client.post(f"/api/models/{model_id}/review", json={"rationale": "review"})
    await client.post(f"/api/models/{model_id}/lock", json={"rationale": "lock"})
    async with session_factory() as session:
        model = await session.get(ModelRecord, model_id)
        assert model is not None
        analysis = await session.get(Analysis, model.analysis_id)
        assert analysis is not None
        project_id = analysis.project_id
    assay = (
        await client.post(
            "/api/assay-projects",
            json={
                "project_id": project_id,
                "name": "Locked endpoint bridge",
                "proposed_purpose": "Research-only pipeline bridge.",
                "specimen_type": "synthetic paired expression",
                "biological_context": "Synthetic paired bridge validation.",
                "proposed_output": "locked classifier score and call",
                "current_stage": "VALIDATE",
                "assay_version": "demo-1.0",
            },
        )
    ).json()
    question = (
        await client.post(
            f"/api/assay-projects/{assay['id']}/questions",
            json={
                "question_key": "paired_bridging_equivalence",
                "formal_question": "Is pipeline B equivalent to pipeline A?",
                "source": "USER_SELECTED",
            },
        )
    ).json()
    prepared_id = await _input_limit_bundle(
        session_factory,
        storage,
        project_id,
        tmp_path / "bridge-fixture",
        paired_bridge=True,
    )
    payload = {
        "assay_project_id": assay["id"],
        "question_id": question["id"],
        "model_id": model_id,
        "prepared_dataset_id": prepared_id,
        "name": "Locked endpoint paired bridge",
        "objective": "Evaluate paired equivalence without retraining.",
        "study_type": "PAIRED_BRIDGING",
        "assignments": _bridge_assignments(confounded=True),
        "factors": ["condition", "run"],
        "reference_condition": "pipeline_a",
        "comparator_condition": "pipeline_b",
        "equivalence_margin": 0.05,
        "condition_rationale": "Pipeline A is the locked reference.",
        "criteria": [
            {
                "key": "paired_bias_margin",
                "metric": "paired_bias",
                "endpoint": "classifier_score",
                "operator": "absolute_lte",
                "threshold": 0.05,
                "rationale": "Absolute paired bias must remain within margin.",
            },
            {
                "key": "call_agreement",
                "metric": "categorical_agreement",
                "endpoint": "predicted_class",
                "operator": "gte",
                "threshold": 0.95,
                "rationale": "Categorical calls must remain concordant.",
            },
        ],
        "bootstrap_iterations": 200,
    }
    created = await client.post("/api/studies", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "DESIGN_INVALID"
    assert "STUDY.BRIDGE_CONDITION_RUN_CONFOUNDED" in {
        item["code"] for item in created.json()["design_validation_json"]["errors"]
    }
    repaired = await client.patch(
        f"/api/studies/{created.json()['id']}",
        json={"assignments": _bridge_assignments()},
    )
    assert repaired.status_code == 200
    assert repaired.json()["status"] == "DESIGN_VALID"
    locked = await client.post(f"/api/studies/{created.json()['id']}/lock")
    assert locked.status_code == 200
    assert (
        locked.json()["study_spec_json"]["analysis_plan"]["correlation_passes_equivalence"] is False
    )
    queued = await client.post(f"/api/studies/{created.json()['id']}/run")
    assert queued.status_code == 202
    assert dispatched_study_ids == [queued.json()["run_id"]]


async def test_robustness_interference_design_lock_and_queue(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    dispatched_study_ids: list[str],
    tmp_path: Path,
) -> None:
    model_id = await _candidate(session_factory, storage)
    await client.post(f"/api/models/{model_id}/review", json={"rationale": "review"})
    await client.post(f"/api/models/{model_id}/lock", json={"rationale": "lock"})
    async with session_factory() as session:
        model = await session.get(ModelRecord, model_id)
        assert model is not None
        analysis = await session.get(Analysis, model.analysis_id)
        assert analysis is not None
        project_id = analysis.project_id
    assay = (
        await client.post(
            "/api/assay-projects",
            json={
                "project_id": project_id,
                "name": "Locked endpoint challenge study",
                "proposed_purpose": "Research-only robustness evaluation.",
                "specimen_type": "synthetic paired expression",
                "biological_context": "Synthetic hemoglobin interference.",
                "proposed_output": "locked classifier score and call",
                "current_stage": "VALIDATE",
                "assay_version": "demo-1.0",
            },
        )
    ).json()
    question = (
        await client.post(
            f"/api/assay-projects/{assay['id']}/questions",
            json={
                "question_key": "robustness_interference_validation",
                "formal_question": "Does hemoglobin cause unacceptable endpoint changes?",
                "source": "USER_SELECTED",
            },
        )
    ).json()
    prepared_id = await _input_limit_bundle(
        session_factory,
        storage,
        project_id,
        tmp_path / "robustness-fixture",
        robustness=True,
    )
    created = await client.post(
        "/api/studies",
        json={
            "assay_project_id": assay["id"],
            "question_id": question["id"],
            "model_id": model_id,
            "prepared_dataset_id": prepared_id,
            "name": "Hemoglobin challenge",
            "objective": "Quantify challenge effects without retraining.",
            "study_type": "ROBUSTNESS_INTERFERENCE",
            "assignments": _bridge_assignments(robustness=True),
            "factors": ["condition", "challenge_type", "run"],
            "reference_condition": "pipeline_a",
            "comparator_condition": "pipeline_b",
            "equivalence_margin": 0.05,
            "condition_rationale": "Pipeline A is the unchallenged reference.",
            "criteria": [
                {
                    "key": "challenge_effect_margin",
                    "metric": "mean_challenge_effect",
                    "endpoint": "classifier_score",
                    "operator": "absolute_lte",
                    "threshold": 0.05,
                    "rationale": "Mean challenge effect must remain within margin.",
                },
                {
                    "key": "call_change_rate",
                    "metric": "call_change_rate",
                    "endpoint": "predicted_class",
                    "operator": "lte",
                    "threshold": 0.05,
                    "rationale": "Call changes must remain uncommon.",
                },
            ],
            "bootstrap_iterations": 200,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "DESIGN_VALID"
    locked = await client.post(f"/api/studies/{created.json()['id']}/lock")
    assert locked.status_code == 200
    assert (
        locked.json()["study_spec_json"]["analysis_plan"]["biological_specificity_claims_supported"]
        is False
    )
    queued = await client.post(f"/api/studies/{created.json()['id']}/run")
    assert queued.status_code == 202
    assert dispatched_study_ids == [queued.json()["run_id"]]
