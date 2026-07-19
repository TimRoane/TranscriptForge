"""Durable Nextflow execution for post-lock analytical validation studies."""

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
from sqlalchemy import select

from transcriptforge_api.config import Settings, get_settings
from transcriptforge_api.models import (
    AcceptanceCriterion,
    AnalyticalStudy,
    Artifact,
    AssayAuditEvent,
    Recommendation,
    Run,
    ValidationResult,
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
class StudyRunSnapshot:
    id: str
    study_id: str
    prepared_dataset_id: str
    params_uri: str
    profile: str


MANIFEST_SCHEMA = (
    Path(__file__).parents[4]
    / "contracts"
    / "validation"
    / "validation_bundle_manifest.schema.json"
)


def run_assay_study_workflow(
    run_id: str,
    *,
    settings: Settings | None = None,
    storage: StorageBackend | None = None,
) -> dict[str, Any]:
    """Stage frozen inputs, run one analytical study, and persist its evidence."""
    settings = settings or get_settings()
    storage = storage or get_storage_backend()
    snapshot = asyncio.run(_mark_starting(settings, run_id))
    try:
        frozen = json.loads(storage.read_bytes(snapshot.params_uri))
        run_root = _confined_run_root(settings.run_work_root, run_id)
        input_dir = run_root / "input"
        output_dir = run_root / "output"
        work_dir = run_root / "work"
        provenance_dir = run_root / "provenance"
        for directory in (input_dir, output_dir, work_dir, provenance_dir):
            directory.mkdir(parents=True, exist_ok=True)
        staged = {
            "study_spec": _stage(storage, frozen["study_spec"], input_dir / "study_spec.json"),
            "study_assignments": _stage(
                storage,
                frozen["study_assignments"],
                input_dir / "study_assignments.tsv",
            ),
            "expression_bundle": _stage(
                storage,
                frozen["expression_bundle"],
                input_dir / "expression_bundle.tar.gz",
            ),
            "model": _stage(storage, frozen["model"], input_dir / "model.json"),
            "model_manifest": _stage(
                storage, frozen["model_manifest"], input_dir / "model_manifest.json"
            ),
        }
        params = input_dir / "nextflow-params.json"
        params.write_text(
            json.dumps(
                {
                    **{key: str(value) for key, value in staged.items()},
                    "analysis_python": sys.executable,
                    "outdir": str(output_dir),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        run_name = f"tf_study_{run_id.replace('-', '_')}"
        effective_work = _nextflow_work_dir(settings, snapshot.profile, snapshot.id, work_dir)
        command = [
            settings.nextflow_executable,
            "run",
            str(settings.pipeline_path.resolve()),
            "-entry",
            "RUN_ASSAY_STUDY",
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
        log_path = run_root / ".nextflow.log"
        log_text = log_path.read_text(encoding="utf-8") if log_path.is_file() else ""
        session_id = _session_id(completed.stdout + completed.stderr + log_text)
        if completed.returncode != 0:
            raise RuntimeError(
                f"Nextflow exited with code {completed.returncode}: "
                f"{_error_tail(completed.stdout or log_text or completed.stderr)}"
            )
        raise_if_cancelled(run_root)
        bundle_root = output_dir / "study/results/validation_bundle"
        archive = output_dir / "study/results/validation_bundle.tar.gz"
        required = (
            bundle_root / "manifest.json",
            bundle_root / "decision/decision_summary.json",
            bundle_root / "metrics/acceptance_results.json",
            archive,
        )
        if any(not path.is_file() for path in required):
            raise RuntimeError("Study completed without a complete Validation Bundle.")
        manifest = json.loads(required[0].read_text(encoding="utf-8"))
        Draft202012Validator(json.loads(MANIFEST_SCHEMA.read_text())).validate(manifest)
        if manifest["study_id"] != snapshot.study_id or manifest["model_retrained"] is not False:
            raise RuntimeError("Validation Bundle identity or locked-model policy is invalid.")
        decision = json.loads(required[1].read_text(encoding="utf-8"))
        acceptance = json.loads(required[2].read_text(encoding="utf-8"))
        summary = {**decision, "acceptance_results": acceptance, "model_retrained": False}
        if manifest["study_type"] == "PRECISION_REPRODUCIBILITY":
            summary.update(
                {
                    "precision": json.loads(
                        (bundle_root / "metrics/precision_metrics.json").read_text()
                    ),
                    "variance_components": json.loads(
                        (bundle_root / "metrics/variance_components.json").read_text()
                    ),
                    "agreement": json.loads(
                        (bundle_root / "metrics/agreement_metrics.json").read_text()
                    ),
                }
            )
        elif manifest["study_type"] == "INPUT_DEGRADATION_LIMIT":
            metrics_path = bundle_root / "metrics/input_degradation_metrics.json"
            summary["input_degradation"] = json.loads(metrics_path.read_text())
        elif manifest["study_type"] == "PAIRED_BRIDGING":
            metrics_path = bundle_root / "metrics/paired_bridging_metrics.json"
            summary["paired_bridging"] = json.loads(metrics_path.read_text())
        else:
            metrics_path = bundle_root / "metrics/robustness_interference_metrics.json"
            summary["robustness_interference"] = json.loads(metrics_path.read_text())
        summary["threshold_stability"] = json.loads(
            (bundle_root / "metrics/threshold_stability.json").read_text()
        )
        artifacts = _store_artifacts(storage, run_id, _artifact_specs(run_root))
        asyncio.run(_mark_succeeded(settings, snapshot, artifacts, session_id, summary))
        return {"run_id": run_id, "state": RunState.SUCCEEDED.value}
    except RunCancelled as error:
        asyncio.run(_mark_cancelled(settings, snapshot, error))
        return {"run_id": run_id, "state": RunState.CANCELLED.value}
    except Exception as error:
        asyncio.run(_mark_failed(settings, snapshot, error))
        raise


def _stage(storage: StorageBackend, item: dict[str, Any], destination: Path) -> Path:
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("wb") as output:
        storage.download(str(item["storage_uri"]), output)
    actual = hashlib.sha256(temporary.read_bytes()).hexdigest()
    if actual != item["sha256"]:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Staged {destination.name} checksum does not match.")
    temporary.replace(destination)
    return destination


def _artifact_specs(run_root: Path) -> list[ArtifactSpec]:
    root = run_root / "output/study/results/validation_bundle"
    entries = [
        (
            "validation_bundle",
            "Validation Bundle",
            run_root / "output/study/results/validation_bundle.tar.gz",
            "application/gzip",
        ),
        (
            "validation_manifest",
            "Validation Bundle manifest",
            root / "manifest.json",
            "application/json",
        ),
        ("study_specification", "Locked StudySpec", root / "study_spec.yaml", "application/yaml"),
        (
            "locked_model_manifest",
            "Locked ModelManifest",
            root / "model_manifest.json",
            "application/json",
        ),
        (
            "study_assignments",
            "Locked study assignments",
            root / "design/study_assignments.tsv",
            "text/tab-separated-values",
        ),
        (
            "study_design_validation",
            "Study design validation",
            root / "design/design_validation.json",
            "application/json",
        ),
        (
            "study_factor_balance",
            "Study factor balance",
            root / "design/factor_balance.tsv",
            "text/tab-separated-values",
        ),
        (
            "study_confounding",
            "Study confounding matrix",
            root / "design/confounding_matrix.tsv",
            "text/tab-separated-values",
        ),
        (
            "study_endpoints_parquet",
            "Validation endpoints (Parquet)",
            root / "endpoints/endpoint_table.parquet",
            "application/vnd.apache.parquet",
        ),
        (
            "study_endpoints",
            "Validation endpoints (TSV)",
            root / "endpoints/endpoint_table.tsv.gz",
            "application/gzip",
        ),
        (
            "precision_metrics",
            "Precision metrics",
            root / "metrics/precision_metrics.json",
            "application/json",
        ),
        (
            "input_degradation_metrics",
            "Input/degradation limit metrics",
            root / "metrics/input_degradation_metrics.json",
            "application/json",
        ),
        (
            "input_degradation_figure",
            "Locked score stability by ordered level",
            root / "figures/score_stability_by_level.svg",
            "image/svg+xml",
        ),
        (
            "paired_bridging_metrics",
            "Paired bridging metrics",
            root / "metrics/paired_bridging_metrics.json",
            "application/json",
        ),
        (
            "paired_bridge_pairs",
            "Paired bridge results",
            root / "endpoints/paired_bridge_results.tsv",
            "text/tab-separated-values",
        ),
        (
            "paired_bridge_bland_altman",
            "Paired bridge Bland-Altman plot",
            root / "figures/paired_bridge_bland_altman.svg",
            "image/svg+xml",
        ),
        (
            "robustness_interference_metrics",
            "Robustness/interference metrics",
            root / "metrics/robustness_interference_metrics.json",
            "application/json",
        ),
        (
            "challenge_pair_results",
            "Challenge/reference pair results",
            root / "endpoints/challenge_pair_results.tsv",
            "text/tab-separated-values",
        ),
        (
            "challenge_effect_figure",
            "Paired challenge-effect plot",
            root / "figures/challenge_effect_plot.svg",
            "image/svg+xml",
        ),
        (
            "variance_components",
            "Variance components and ICC",
            root / "metrics/variance_components.json",
            "application/json",
        ),
        (
            "agreement_metrics",
            "Categorical agreement metrics",
            root / "metrics/agreement_metrics.json",
            "application/json",
        ),
        (
            "threshold_stability",
            "Decision-threshold stability",
            root / "metrics/threshold_stability.json",
            "application/json",
        ),
        (
            "acceptance_results",
            "Prespecified acceptance results",
            root / "metrics/acceptance_results.json",
            "application/json",
        ),
        (
            "validation_decision_summary",
            "Validation decision summary",
            root / "decision/decision_summary.json",
            "application/json",
        ),
        (
            "validation_recommendations",
            "Validation next actions",
            root / "decision/recommendations.json",
            "application/json",
        ),
        (
            "validation_report",
            "Validation report",
            root / "report/validation_report.html",
            "text/html",
        ),
        (
            "validation_report_pdf",
            "Validation report (PDF)",
            root / "report/validation_report.pdf",
            "application/pdf",
        ),
        (
            "nextflow_trace",
            "Nextflow trace",
            run_root / "provenance/trace.tsv",
            "text/tab-separated-values",
        ),
        (
            "nextflow_report",
            "Nextflow execution report",
            run_root / "provenance/execution_report.html",
            "text/html",
        ),
        (
            "nextflow_timeline",
            "Nextflow timeline",
            run_root / "provenance/timeline.html",
            "text/html",
        ),
        ("nextflow_dag", "Nextflow DAG", run_root / "provenance/dag.html", "text/html"),
        ("nextflow_stdout", "Nextflow stdout", run_root / "provenance/stdout.log", "text/plain"),
        ("nextflow_stderr", "Nextflow stderr", run_root / "provenance/stderr.log", "text/plain"),
    ]
    return [
        ArtifactSpec(kind, title, path, mime, index + 1)
        for index, (kind, title, path, mime) in enumerate(entries)
        if path.is_file()
    ]


async def _mark_starting(settings: Settings, run_id: str) -> StudyRunSnapshot:
    async with _worker_session(settings) as session:
        run = await session.get(Run, run_id)
        if (
            run is None
            or run.study_id is None
            or run.prepared_dataset_id is None
            or run.run_type != RunType.ASSAY_STUDY.value
        ):
            raise RuntimeError(f"Analytical Study run '{run_id}' does not exist.")
        if run.state in {RunState.CANCELLING.value, RunState.CANCELLED.value}:
            raise RunCancelled("Cancelled by user.")
        if run.state != RunState.QUEUED.value:
            raise RuntimeError(f"Analytical Study run '{run_id}' is not QUEUED.")
        study = await session.get(AnalyticalStudy, run.study_id)
        if study is None:
            raise RuntimeError("Analytical Study disappeared before execution.")
        run.state = RunState.STARTING.value
        run.started_at = datetime.now(UTC)
        study.status = "RUNNING"
        await session.commit()
        return StudyRunSnapshot(
            run.id, run.study_id, run.prepared_dataset_id, run.params_uri, run.profile
        )


async def _mark_running(settings: Settings, snapshot: StudyRunSnapshot, run_name: str) -> None:
    async with _worker_session(settings) as session:
        run = await session.get(Run, snapshot.id)
        if run is None:
            raise RuntimeError("Analytical Study run disappeared.")
        if run.state in {RunState.CANCELLING.value, RunState.CANCELLED.value}:
            raise RunCancelled("Cancelled by user.")
        run.state = RunState.RUNNING.value
        run.nextflow_run_name = run_name
        await session.commit()


async def _mark_succeeded(
    settings: Settings,
    snapshot: StudyRunSnapshot,
    artifacts: list[dict[str, Any]],
    session_id: str | None,
    summary: dict[str, Any],
) -> None:
    async with _worker_session(settings) as session:
        run = await session.get(Run, snapshot.id)
        study = await session.get(AnalyticalStudy, snapshot.study_id)
        if run is None or study is None:
            raise RuntimeError("Analytical Study or run disappeared before completion.")
        if run.state in {RunState.CANCELLING.value, RunState.CANCELLED.value}:
            raise RunCancelled("Cancelled by user.")
        for item in artifacts:
            session.add(Artifact(run_id=run.id, metadata_json={}, **item))
        by_type = {item["artifact_type"]: item for item in artifacts}
        bundle = by_type["validation_bundle"]
        study.validation_bundle_uri = bundle["storage_uri"]
        study.status = "SUCCEEDED"
        study.completed_at = datetime.now(UTC)
        run.state = RunState.SUCCEEDED.value
        run.exit_code = 0
        run.nextflow_session_id = session_id
        run.finished_at = datetime.now(UTC)
        session.add(
            ValidationResult(
                study_id=study.id,
                run_id=run.id,
                overall_status=summary["overall_status"],
                summary_json=summary,
                bundle_uri=bundle["storage_uri"],
                bundle_sha256=bundle["sha256"],
            )
        )
        criteria = list(
            await session.scalars(
                select(AcceptanceCriterion).where(AcceptanceCriterion.study_id == study.id)
            )
        )
        observed_by_key = {item["key"]: item for item in summary["acceptance_results"]["criteria"]}
        for criterion in criteria:
            result = observed_by_key[criterion.key]
            criterion.result_status = result["status"]
            criterion.observed_json = {
                "value": result["observed"],
                "uncertainty": result["uncertainty"],
                "population": result["population"],
            }
        session.add(
            Recommendation(
                assay_project_id=study.assay_project_id,
                source_type="STUDY",
                source_id=study.id,
                rule_id=f"VALIDATION.PRECISION.{summary['overall_status']}",
                recommendation_type="REVIEW_VALIDATION_EVIDENCE",
                title="Review the locked precision evidence",
                summary=("Review every prespecified criterion and document the assay decision."),
                why="Study-level status must not conceal individual criterion results.",
                what_it_resolves=(
                    "Whether the tested precision evidence supports the next declared step."
                ),
                stage="VALIDATE",
                priority=90,
                requirement_level="STRONGLY_RECOMMENDED",
                status="OPEN",
                required_inputs_json=["scientist rationale"],
                expected_output="A traceable scientist decision; no automatic clinical claim.",
                proposed_action_json={"action_type": "VIEW_STUDY_RESULT", "study_id": study.id},
                evidence_refs_json=[{"type": "validation_result", "run_id": run.id}],
                assumptions_json=[],
                limitations_json=list(summary.get("limitations", [])),
                alternative_action_ids_json=[],
            )
        )
        session.add(
            AssayAuditEvent(
                assay_project_id=study.assay_project_id,
                event_type="ANALYTICAL_STUDY_COMPLETED",
                actor="local-user",
                object_type="AnalyticalStudy",
                object_id=study.id,
                revision=study.current_revision,
                hashes_json={"validation_bundle_sha256": bundle["sha256"]},
                details_json={
                    "run_id": run.id,
                    "overall_status": summary["overall_status"],
                    "model_retrained": False,
                },
            )
        )
        await session.commit()


async def _mark_cancelled(
    settings: Settings, snapshot: StudyRunSnapshot, error: RunCancelled
) -> None:
    async with _worker_session(settings) as session:
        run = await session.get(Run, snapshot.id)
        study = await session.get(AnalyticalStudy, snapshot.study_id)
        if run is not None:
            run.state = RunState.CANCELLED.value
            run.exit_code = 143
            run.error_summary = str(error)[:4000]
            run.finished_at = datetime.now(UTC)
        if study is not None:
            study.status = "CANCELLED"
        await session.commit()


async def _mark_failed(settings: Settings, snapshot: StudyRunSnapshot, error: Exception) -> None:
    async with _worker_session(settings) as session:
        run = await session.get(Run, snapshot.id)
        study = await session.get(AnalyticalStudy, snapshot.study_id)
        if run is not None:
            run.state = RunState.FAILED.value
            run.exit_code = getattr(error, "returncode", None)
            run.error_summary = str(error)[:4000]
            run.finished_at = datetime.now(UTC)
        if study is not None:
            study.status = "FAILED"
        await session.commit()
