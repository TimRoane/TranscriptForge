"""Durable Nextflow execution for locked pre-lock Development Experiments."""

import asyncio
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from transcriptforge_api.config import Settings, get_settings
from transcriptforge_api.models import (
    Artifact,
    AssayAuditEvent,
    ExperimentPlan,
    Recommendation,
    Run,
)
from transcriptforge_api.models.enums import RunState, RunType
from transcriptforge_api.storage import get_storage_backend
from transcriptforge_api.storage.base import StorageBackend
from transcriptforge_api.workers.process_control import (
    RunCancelled,
    raise_if_cancelled,
    run_cancellable,
)
from transcriptforge_api.workers.validation import (
    ArtifactSpec,
    _confined_run_root,
    _error_tail,
    _nextflow_work_dir,
    _session_id,
    _store_artifacts,
    _worker_session,
)


@dataclass(frozen=True, slots=True)
class ExperimentRunSnapshot:
    id: str
    experiment_id: str
    prepared_dataset_id: str
    params_uri: str
    profile: str


CONTRACT_ROOT = Path(__file__).parents[4] / "contracts" / "experiment"


def _validate_contract(payload: dict[str, Any], schema_name: str, label: str) -> None:
    schema = json.loads((CONTRACT_ROOT / schema_name).read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda item: list(item.path),
    )
    if errors:
        location = ".".join(str(value) for value in errors[0].path) or "document"
        raise RuntimeError(f"{label} violates its contract at {location}: {errors[0].message}")


def run_assay_experiment_workflow(
    run_id: str,
    *,
    settings: Settings | None = None,
    storage: StorageBackend | None = None,
) -> dict[str, Any]:
    """Stage immutable inputs, run the experiment workflow, and index evidence."""
    settings = settings or get_settings()
    storage = storage or get_storage_backend()
    try:
        snapshot = asyncio.run(_mark_starting(settings, run_id))
    except RunCancelled:
        return {"run_id": run_id, "state": RunState.CANCELLED.value}
    try:
        frozen = json.loads(storage.read_bytes(snapshot.params_uri))
        run_root = _confined_run_root(settings.run_work_root, run_id)
        input_dir = run_root / "input"
        output_dir = run_root / "output"
        work_dir = run_root / "work"
        provenance_dir = run_root / "provenance"
        for directory in (input_dir, output_dir, work_dir, provenance_dir):
            directory.mkdir(parents=True, exist_ok=True)
        spec = _stage_object(
            storage,
            frozen["experiment_spec"],
            input_dir / "experiment_spec.json",
        )
        assignments = _stage_object(
            storage,
            frozen["experiment_assignments"],
            input_dir / "experiment_assignments.tsv",
        )
        bundle = _stage_object(
            storage,
            frozen["expression_bundle"],
            input_dir / "expression_bundle.tar.gz",
        )
        params = input_dir / "nextflow-params.json"
        params.write_text(
            json.dumps(
                {
                    "experiment_spec": str(spec),
                    "experiment_assignments": str(assignments),
                    "expression_bundle": str(bundle),
                    "analysis_python": sys.executable,
                    "outdir": str(output_dir),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        run_name = f"tf_experiment_{run_id.replace('-', '_')}"
        effective_work = _nextflow_work_dir(settings, snapshot.profile, snapshot.id, work_dir)
        command = [
            settings.nextflow_executable,
            "run",
            str(settings.pipeline_path.resolve()),
            "-entry",
            "RUN_ASSAY_EXPERIMENT",
            "-profile",
            snapshot.profile,
            "-params-file",
            str(params),
            "-work-dir",
            effective_work,
            "-name",
            run_name,
            "-with-trace",
            str(provenance_dir / "trace.tsv"),
            "-with-report",
            str(provenance_dir / "execution_report.html"),
            "-with-timeline",
            str(provenance_dir / "timeline.html"),
            "-with-dag",
            str(provenance_dir / "dag.html"),
        ]
        asyncio.run(_mark_running(settings, snapshot, run_name))
        environment = os.environ.copy()
        environment["NXF_HOME"] = str(run_root / ".nextflow")
        completed = run_cancellable(
            command,
            cwd=run_root,
            env=environment,
            run_root=run_root,
            stdout_path=provenance_dir / "stdout.log",
            stderr_path=provenance_dir / "stderr.log",
        )
        nextflow_log = run_root / ".nextflow.log"
        log_text = nextflow_log.read_text(encoding="utf-8") if nextflow_log.is_file() else ""
        session_id = _session_id(completed.stdout + "\n" + completed.stderr + "\n" + log_text)
        if completed.returncode != 0:
            raise RuntimeError(
                f"Nextflow exited with code {completed.returncode}: "
                f"{_error_tail(completed.stdout or log_text or completed.stderr)}"
            )
        raise_if_cancelled(run_root)
        evidence = output_dir / "experiment" / "results" / "development_evidence_bundle"
        manifest_path = evidence / "manifest.json"
        decision_path = evidence / "decision" / "decision_summary.json"
        recommendations_path = evidence / "decision" / "recommendations.json"
        archive_path = output_dir / "experiment" / "results" / "development_evidence_bundle.tar.gz"
        for required in (manifest_path, decision_path, recommendations_path, archive_path):
            if not required.is_file():
                raise RuntimeError(f"Experiment completed without publishing {required.name}.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        _validate_contract(
            manifest,
            "development_evidence_manifest.schema.json",
            "Development Evidence Bundle manifest",
        )
        if (
            manifest.get("bundle_type") != "development_evidence_bundle"
            or manifest.get("experiment_id") != snapshot.experiment_id
        ):
            raise RuntimeError("Development Evidence Bundle identity is invalid.")
        decision_summary = json.loads(decision_path.read_text(encoding="utf-8"))
        _validate_contract(
            decision_summary,
            "decision_summary.schema.json",
            "Development Experiment decision summary",
        )
        recommendations = json.loads(recommendations_path.read_text(encoding="utf-8"))
        artifacts = _store_artifacts(storage, run_id, _artifact_specs(run_root))
        asyncio.run(
            _mark_succeeded(
                settings,
                snapshot,
                artifacts,
                session_id,
                decision_summary,
                recommendations,
            )
        )
        return {"run_id": run_id, "state": RunState.SUCCEEDED.value}
    except RunCancelled as error:
        asyncio.run(_mark_cancelled(settings, snapshot, error))
        return {"run_id": run_id, "state": RunState.CANCELLED.value}
    except Exception as error:
        asyncio.run(_mark_failed(settings, snapshot, error))
        raise


def _stage_object(storage: StorageBackend, item: dict[str, Any], destination: Path) -> Path:
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("wb") as output:
        storage.download(str(item["storage_uri"]), output)
    digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
    if digest != item["sha256"]:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Staged {destination.name} checksum does not match.")
    temporary.replace(destination)
    return destination


def _artifact_specs(run_root: Path) -> list[ArtifactSpec]:
    evidence = run_root / "output/experiment/results/development_evidence_bundle"
    candidates = [
        ArtifactSpec(
            "development_evidence_bundle",
            "Development Evidence Bundle",
            run_root / "output/experiment/results/development_evidence_bundle.tar.gz",
            "application/gzip",
            1,
        ),
        ArtifactSpec(
            "development_manifest",
            "Development Evidence Bundle manifest",
            evidence / "manifest.json",
            "application/json",
            2,
        ),
        ArtifactSpec(
            "experiment_specification",
            "Locked experiment specification",
            evidence / "experiment_spec.yaml",
            "application/yaml",
            3,
        ),
        ArtifactSpec(
            "experiment_question",
            "Declared experiment question",
            evidence / "question.json",
            "application/json",
            4,
        ),
        ArtifactSpec(
            "experiment_assignments",
            "Locked experiment assignments",
            evidence / "design/experiment_assignments.tsv",
            "text/tab-separated-values",
            5,
        ),
        ArtifactSpec(
            "experiment_design_validation",
            "Experiment design validation",
            evidence / "design/design_validation.json",
            "application/json",
            6,
        ),
        ArtifactSpec(
            "experiment_factor_balance",
            "Experiment factor balance",
            evidence / "design/factor_balance.tsv",
            "text/tab-separated-values",
            7,
        ),
        ArtifactSpec(
            "experiment_confounding_matrix",
            "Experiment confounding matrix",
            evidence / "design/confounding_matrix.tsv",
            "text/tab-separated-values",
            8,
        ),
        ArtifactSpec(
            "experiment_endpoint_parquet",
            "Experiment endpoint table (Parquet)",
            evidence / "endpoints/endpoint_table.parquet",
            "application/vnd.apache.parquet",
            9,
        ),
        ArtifactSpec(
            "experiment_endpoint_table",
            "Experiment endpoint table (TSV)",
            evidence / "endpoints/endpoint_table.tsv.gz",
            "application/gzip",
            10,
        ),
        ArtifactSpec(
            "experiment_excluded_measurements",
            "Excluded experiment measurements",
            evidence / "endpoints/excluded_measurements.tsv",
            "text/tab-separated-values",
            11,
        ),
        ArtifactSpec(
            "experiment_primary_results",
            "Primary experiment results",
            evidence / "results/primary_results.json",
            "application/json",
            12,
        ),
        ArtifactSpec(
            "experiment_secondary_results",
            "Secondary experiment results",
            evidence / "results/secondary_results.json",
            "application/json",
            13,
        ),
        ArtifactSpec(
            "experiment_sensitivity_results",
            "Experiment sensitivity results",
            evidence / "results/sensitivity_results.json",
            "application/json",
            14,
        ),
        ArtifactSpec(
            "experiment_model_summaries",
            "Experiment model summaries",
            evidence / "results/model_summaries.json",
            "application/json",
            15,
        ),
        ArtifactSpec(
            "experiment_decision_summary",
            "Development decision summary",
            evidence / "decision/decision_summary.json",
            "application/json",
            16,
        ),
        ArtifactSpec(
            "experiment_decision_summary_markdown",
            "Development decision summary (Markdown)",
            evidence / "decision/decision_summary.md",
            "text/markdown",
            17,
        ),
        ArtifactSpec(
            "experiment_recommendations",
            "Development next-action recommendations",
            evidence / "decision/recommendations.json",
            "application/json",
            18,
        ),
        ArtifactSpec(
            "experiment_unresolved_questions",
            "Unresolved development questions",
            evidence / "decision/unresolved_questions.json",
            "application/json",
            19,
        ),
        ArtifactSpec(
            "experiment_profile_stability_figure",
            "Profile stability by RNA input",
            evidence / "figures/profile_stability_by_input.svg",
            "image/svg+xml",
            20,
        ),
        ArtifactSpec(
            "experiment_paired_differences",
            "Paired condition differences",
            evidence / "results/paired_differences.tsv",
            "text/tab-separated-values",
            20,
        ),
        ArtifactSpec(
            "experiment_bland_altman_figure",
            "Paired Bland-Altman comparison",
            evidence / "figures/bland_altman.svg",
            "image/svg+xml",
            20,
        ),
        ArtifactSpec(
            "experiment_pair_correlation_figure",
            "Profile correlation by biological pair",
            evidence / "figures/profile_correlation_by_pair.svg",
            "image/svg+xml",
            20,
        ),
        ArtifactSpec(
            "development_report",
            "Development Experiment report",
            evidence / "report/development_report.html",
            "text/html",
            21,
        ),
        ArtifactSpec(
            "development_report_pdf",
            "Development Experiment report (PDF)",
            evidence / "report/development_report.pdf",
            "application/pdf",
            22,
        ),
        ArtifactSpec(
            "experiment_input_checksums",
            "Experiment input checksums",
            evidence / "provenance/input_checksums.tsv",
            "text/tab-separated-values",
            23,
        ),
        ArtifactSpec(
            "experiment_software_versions",
            "Experiment software versions",
            evidence / "provenance/software_versions.yml",
            "application/yaml",
            24,
        ),
        ArtifactSpec(
            "experiment_container_digests",
            "Experiment container digests",
            evidence / "provenance/container_digests.tsv",
            "text/tab-separated-values",
            25,
        ),
        ArtifactSpec(
            "experiment_parameters",
            "Experiment runtime parameters",
            evidence / "provenance/parameters.json",
            "application/json",
            26,
        ),
        ArtifactSpec(
            "nextflow_trace",
            "Nextflow trace",
            run_root / "provenance/trace.tsv",
            "text/tab-separated-values",
            40,
        ),
        ArtifactSpec(
            "nextflow_report",
            "Nextflow execution report",
            run_root / "provenance/execution_report.html",
            "text/html",
            41,
        ),
        ArtifactSpec(
            "nextflow_timeline",
            "Nextflow timeline",
            run_root / "provenance/timeline.html",
            "text/html",
            42,
        ),
        ArtifactSpec(
            "nextflow_dag",
            "Nextflow DAG",
            run_root / "provenance/dag.html",
            "text/html",
            43,
        ),
        ArtifactSpec(
            "nextflow_stdout",
            "Nextflow stdout",
            run_root / "provenance/stdout.log",
            "text/plain",
            44,
        ),
        ArtifactSpec(
            "nextflow_stderr",
            "Nextflow stderr",
            run_root / "provenance/stderr.log",
            "text/plain",
            45,
        ),
    ]
    return [item for item in candidates if item.path.is_file()]


async def _mark_starting(settings: Settings, run_id: str) -> ExperimentRunSnapshot:
    async with _worker_session(settings) as session:
        run = await session.get(Run, run_id)
        if (
            run is None
            or run.experiment_id is None
            or run.prepared_dataset_id is None
            or run.run_type != RunType.ASSAY_EXPERIMENT
        ):
            raise RuntimeError(f"Development Experiment run '{run_id}' does not exist.")
        if run.state in {RunState.CANCELLING, RunState.CANCELLED}:
            raise RunCancelled("Cancelled by user.")
        if run.state != RunState.QUEUED:
            raise RuntimeError(f"Experiment run '{run_id}' is not QUEUED.")
        experiment = await session.get(ExperimentPlan, run.experiment_id)
        if experiment is None:
            raise RuntimeError("Development Experiment disappeared before execution.")
        run.state = RunState.STARTING
        run.started_at = datetime.now(UTC)
        experiment.status = "RUNNING"
        await session.commit()
        return ExperimentRunSnapshot(
            run.id,
            run.experiment_id,
            run.prepared_dataset_id,
            run.params_uri,
            run.profile,
        )


async def _mark_running(settings: Settings, snapshot: ExperimentRunSnapshot, run_name: str) -> None:
    async with _worker_session(settings) as session:
        run = await session.get(Run, snapshot.id)
        if run is None:
            raise RuntimeError("Development Experiment run disappeared.")
        if run.state in {RunState.CANCELLING, RunState.CANCELLED}:
            raise RunCancelled("Cancelled by user.")
        run.state = RunState.RUNNING
        run.nextflow_run_name = run_name
        await session.commit()


async def _mark_succeeded(
    settings: Settings,
    snapshot: ExperimentRunSnapshot,
    artifacts: list[dict[str, Any]],
    session_id: str | None,
    decision_summary: dict[str, Any],
    recommendations: dict[str, Any],
) -> None:
    async with _worker_session(settings) as session:
        run = await session.get(Run, snapshot.id)
        experiment = await session.get(ExperimentPlan, snapshot.experiment_id)
        if run is None or experiment is None:
            raise RuntimeError("Experiment or run disappeared before completion.")
        if run.state in {RunState.CANCELLING, RunState.CANCELLED}:
            raise RunCancelled("Cancelled by user.")
        for item in artifacts:
            session.add(Artifact(run_id=run.id, metadata_json={}, **item))
        artifact_by_type = {item["artifact_type"]: item for item in artifacts}
        experiment.development_bundle_uri = artifact_by_type["development_evidence_bundle"][
            "storage_uri"
        ]
        experiment.status = "SUCCEEDED"
        experiment.completed_at = datetime.now(UTC)
        run.state = RunState.SUCCEEDED
        run.exit_code = 0
        run.nextflow_session_id = session_id
        run.finished_at = datetime.now(UTC)
        session.add(
            AssayAuditEvent(
                assay_project_id=experiment.assay_project_id,
                event_type="EXPERIMENT_RUN_COMPLETED",
                actor="local-user",
                object_type="ExperimentPlan",
                object_id=experiment.id,
                revision=experiment.current_revision,
                hashes_json={
                    "development_bundle_sha256": artifact_by_type["development_evidence_bundle"][
                        "sha256"
                    ]
                },
                details_json={"run_id": run.id, "state": "SUCCEEDED"},
            )
        )
        session.add(
            AssayAuditEvent(
                assay_project_id=experiment.assay_project_id,
                event_type="DECISION_SUMMARY_CREATED",
                actor="local-user",
                object_type="ExperimentPlan",
                object_id=experiment.id,
                revision=experiment.current_revision,
                hashes_json={},
                details_json={"finding": decision_summary.get("finding")},
            )
        )
        created_recommendations = []
        for payload in recommendations.get("recommendations", []):
            recommendation = Recommendation(
                assay_project_id=experiment.assay_project_id,
                source_type="EXPERIMENT",
                source_id=experiment.id,
                rule_id=str(payload["rule_id"]),
                recommendation_type="CREATE_EXPERIMENT",
                title=str(payload["title"]),
                summary=str(payload["what_to_do"]),
                why=str(payload["why"]),
                what_it_resolves=str(payload["what_it_resolves"]),
                stage="FEASIBILITY",
                priority=int(payload["priority"]),
                requirement_level=str(payload["requirement_level"]),
                status="OPEN",
                required_inputs_json=list(payload["required_inputs"]),
                expected_output=str(payload["expected_output"]),
                proposed_action_json=dict(payload["one_click_action_template"]),
                evidence_refs_json=list(payload["evidence"]),
                assumptions_json=[],
                limitations_json=list(payload["known_limitations"]),
                alternative_action_ids_json=[],
            )
            session.add(recommendation)
            created_recommendations.append(recommendation)
        await session.flush()
        for recommendation in created_recommendations:
            session.add(
                AssayAuditEvent(
                    assay_project_id=experiment.assay_project_id,
                    event_type="RECOMMENDATION_CREATED",
                    actor="local-user",
                    object_type="Recommendation",
                    object_id=recommendation.id,
                    revision=experiment.current_revision,
                    hashes_json={},
                    details_json={
                        "source_type": "EXPERIMENT",
                        "source_id": experiment.id,
                        "rule_id": recommendation.rule_id,
                    },
                )
            )
        await session.commit()


async def _mark_cancelled(
    settings: Settings, snapshot: ExperimentRunSnapshot, error: RunCancelled
) -> None:
    async with _worker_session(settings) as session:
        run = await session.get(Run, snapshot.id)
        experiment = await session.get(ExperimentPlan, snapshot.experiment_id)
        if run is not None:
            run.state = RunState.CANCELLED
            run.exit_code = 143
            run.error_summary = str(error)[:4000]
            run.finished_at = datetime.now(UTC)
        if experiment is not None:
            experiment.status = "CANCELLED"
        await session.commit()


async def _mark_failed(
    settings: Settings, snapshot: ExperimentRunSnapshot, error: Exception
) -> None:
    async with _worker_session(settings) as session:
        run = await session.get(Run, snapshot.id)
        experiment = await session.get(ExperimentPlan, snapshot.experiment_id)
        if run is not None:
            run.state = RunState.FAILED
            run.exit_code = getattr(error, "returncode", None)
            run.error_summary = str(error)[:4000]
            run.finished_at = datetime.now(UTC)
        if experiment is not None:
            experiment.status = "FAILED"
        await session.commit()
