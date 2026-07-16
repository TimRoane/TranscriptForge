"""Durable worker execution for dataset matrix validation."""

import asyncio
import hashlib
import json
import os
import re
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from transcriptforge_api.config import Settings, get_settings
from transcriptforge_api.models import Artifact, Dataset, PreparedDataset, Run
from transcriptforge_api.models.enums import DatasetStatus, RunState, RunType
from transcriptforge_api.storage import get_storage_backend
from transcriptforge_api.storage.base import StorageBackend

SESSION_PATTERN = re.compile(r"Session UUID:\s*([a-fA-F0-9-]+)")


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    id: str
    dataset_id: str
    params_uri: str
    profile: str
    run_type: str = RunType.DATASET_VALIDATION.value


@asynccontextmanager
async def _worker_session(settings: Settings) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


def run_validation_workflow(
    run_id: str,
    *,
    settings: Settings | None = None,
    storage: StorageBackend | None = None,
) -> dict[str, Any]:
    """Stage immutable inputs, launch Nextflow, and index published contracts."""
    settings = settings or get_settings()
    storage = storage or get_storage_backend()
    snapshot = asyncio.run(_mark_starting(settings, run_id))
    frozen = json.loads(storage.read_bytes(snapshot.params_uri))
    previous_status = str(frozen["dataset"]["status_before_validation"])

    try:
        run_root = _confined_run_root(settings.run_work_root, run_id)
        input_dir = run_root / "input"
        output_dir = run_root / "output"
        work_dir = run_root / "work"
        provenance_dir = run_root / "provenance"
        for directory in (input_dir, output_dir, work_dir, provenance_dir):
            directory.mkdir(parents=True, exist_ok=True)

        matrix_role = (
            "count_matrix"
            if frozen["dataset"]["source_kind"] == "count_matrix"
            else "expression_matrix"
        )
        matrix = _stage_input(storage, frozen["inputs"][matrix_role], input_dir, "matrix")
        metadata = _stage_input(
            storage, frozen["inputs"]["sample_metadata"], input_dir, "metadata"
        )
        validation_config = input_dir / "validation-config.json"
        validation_payload = _validation_config(frozen, matrix, metadata)
        validation_config.write_text(
            json.dumps(validation_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        launcher_params = input_dir / "nextflow-params.json"
        launcher_params.write_text(
            json.dumps(
                {
                    "validation_config": str(validation_config),
                    "matrix": str(matrix),
                    "metadata": str(metadata),
                    "outdir": str(output_dir),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        run_name = f"tf_{run_id.replace('-', '_')}"
        command = build_nextflow_command(
            settings,
            snapshot,
            launcher_params,
            work_dir,
            provenance_dir,
            run_name,
        )
        asyncio.run(_mark_running(settings, run_id, run_name))
        environment = os.environ.copy()
        environment["NXF_HOME"] = str(run_root / ".nextflow")
        completed = subprocess.run(
            command,
            cwd=run_root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        (provenance_dir / "stdout.log").write_text(completed.stdout, encoding="utf-8")
        (provenance_dir / "stderr.log").write_text(completed.stderr, encoding="utf-8")
        nextflow_log = run_root / ".nextflow.log"
        log_text = nextflow_log.read_text(encoding="utf-8") if nextflow_log.is_file() else ""
        session_id = _session_id(completed.stdout + "\n" + completed.stderr + "\n" + log_text)
        if completed.returncode != 0:
            raise RuntimeError(
                f"Nextflow exited with code {completed.returncode}: "
                f"{_error_tail(completed.stderr or completed.stdout)}"
            )

        report_path = output_dir / "validation" / "validation_report.json"
        if not report_path.is_file():
            raise RuntimeError("Nextflow completed without publishing validation_report.json.")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        bundle_summary: dict[str, Any] | None = None
        if snapshot.run_type == RunType.DATASET_PREPARATION.value and report["status"] == "VALID":
            summary_path = output_dir / "preparation" / "prepared" / "bundle_summary.json"
            if not summary_path.is_file():
                raise RuntimeError("Preparation completed without publishing bundle_summary.json.")
            bundle_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        artifact_specs = _artifact_specs(run_root, report_path)
        artifacts = _store_artifacts(storage, run_id, artifact_specs)
        if report["status"] == "INVALID":
            dataset_status = DatasetStatus.INVALID.value
        elif snapshot.run_type == RunType.DATASET_PREPARATION.value:
            dataset_status = DatasetStatus.PREPARED.value
        else:
            dataset_status = DatasetStatus.VALID.value
        asyncio.run(
            _mark_succeeded(
                settings,
                snapshot,
                artifacts,
                dataset_status=dataset_status,
                session_id=session_id,
                bundle_summary=bundle_summary,
            )
        )
        return {"run_id": run_id, "state": RunState.SUCCEEDED.value, "status": report["status"]}
    except Exception as error:
        asyncio.run(_mark_failed(settings, snapshot, previous_status, error))
        raise


def build_nextflow_command(
    settings: Settings,
    snapshot: RunSnapshot,
    params_path: Path,
    work_dir: Path,
    provenance_dir: Path,
    run_name: str,
) -> list[str]:
    """Build a shell-free, auditable Nextflow invocation."""
    entry = (
        "PREPARE_DATASET"
        if snapshot.run_type == RunType.DATASET_PREPARATION.value
        else "VALIDATE_DATASET"
    )
    return [
        settings.nextflow_executable,
        "run",
        str(settings.pipeline_path.resolve()),
        "-entry",
        entry,
        "-profile",
        snapshot.profile,
        "-params-file",
        str(params_path),
        "-work-dir",
        str(work_dir),
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


def _confined_run_root(root: Path, run_id: str) -> Path:
    resolved_root = root.expanduser().resolve()
    resolved = (resolved_root / run_id).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("Run identifier escapes the configured work root.")
    return resolved


def _stage_input(
    storage: StorageBackend, item: dict[str, Any], input_dir: Path, stem: str
) -> Path:
    suffixes = "".join(Path(str(item["original_name"])).suffixes[-2:])
    target = input_dir / f"{stem}{suffixes}"
    digest = hashlib.sha256()
    temporary = target.with_name(f".{target.name}.tmp")
    with temporary.open("wb") as destination:
        storage.download(str(item["storage_uri"]), destination)
    with temporary.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != item["sha256"]:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Staged {stem} checksum does not match its frozen input.")
    temporary.replace(target)
    return target


def _validation_config(frozen: dict[str, Any], matrix: Path, metadata: Path) -> dict[str, Any]:
    dataset = frozen["dataset"]
    request = frozen["validation"]
    payload = {
        "dataset_id": dataset["id"],
        "name": dataset["name"],
        "matrix_path": str(matrix),
        "metadata_path": str(metadata),
        "matrix_orientation": request["matrix_orientation"],
        "feature_id_column": request["feature_id_column"],
        "sample_id_column": request["sample_id_column"],
        "value_type": (
            "raw_counts" if dataset["source_kind"] == "count_matrix" else "normalized_expression"
        ),
        "modality": dataset["modality"],
        "source_kind": dataset["source_kind"],
        "organism": dataset["organism"],
        "genome_build": dataset["genome_build"] or "GRCh38",
        "annotation_release": dataset["annotation_release"] or "unspecified",
        "feature_id_type": request["feature_id_type"],
        "strip_ensembl_version": request.get("strip_ensembl_version", False),
    }
    if "prepared_dataset_id" in frozen:
        payload["prepared_dataset_id"] = frozen["prepared_dataset_id"]
        payload["prepared_version"] = frozen["prepared_version"]
    return payload


@dataclass(frozen=True, slots=True)
class ArtifactSpec:
    artifact_type: str
    title: str
    path: Path
    mime_type: str
    display_order: int


def _artifact_specs(run_root: Path, report_path: Path) -> list[ArtifactSpec]:
    preparation = run_root / "output" / "preparation" / "prepared"
    candidates = [
        ArtifactSpec("validation_report", "Validation report", report_path, "application/json", 0),
        ArtifactSpec(
            "dataset_manifest",
            "Dataset Manifest",
            report_path.with_name("dataset_manifest.json"),
            "application/json",
            1,
        ),
        ArtifactSpec(
            "expression_bundle",
            "Expression Bundle",
            preparation / "expression_bundle.tar.gz",
            "application/gzip",
            2,
        ),
        ArtifactSpec(
            "bundle_manifest",
            "Expression Bundle manifest",
            preparation / "bundle_manifest.json",
            "application/json",
            3,
        ),
        ArtifactSpec(
            "bundle_summary",
            "Expression Bundle summary",
            preparation / "bundle_summary.json",
            "application/json",
            4,
        ),
        ArtifactSpec(
            "qc_summary",
            "Dataset QC summary",
            preparation / "qc_summary.json",
            "application/json",
            5,
        ),
        ArtifactSpec(
            "feature_mapping_summary",
            "Feature mapping summary",
            preparation / "feature_mapping_summary.json",
            "application/json",
            6,
        ),
        ArtifactSpec(
            "nextflow_stdout",
            "Nextflow stdout",
            run_root / "provenance/stdout.log",
            "text/plain",
            10,
        ),
        ArtifactSpec(
            "nextflow_stderr",
            "Nextflow stderr",
            run_root / "provenance/stderr.log",
            "text/plain",
            11,
        ),
        ArtifactSpec("nextflow_log", "Nextflow log", run_root / ".nextflow.log", "text/plain", 12),
        ArtifactSpec(
            "nextflow_trace",
            "Nextflow trace",
            run_root / "provenance/trace.tsv",
            "text/tab-separated-values",
            20,
        ),
        ArtifactSpec(
            "nextflow_report",
            "Execution report",
            run_root / "provenance/execution_report.html",
            "text/html",
            21,
        ),
        ArtifactSpec(
            "nextflow_timeline",
            "Execution timeline",
            run_root / "provenance/timeline.html",
            "text/html",
            22,
        ),
        ArtifactSpec(
            "nextflow_dag",
            "Execution DAG",
            run_root / "provenance/dag.html",
            "text/html",
            23,
        ),
    ]
    return [item for item in candidates if item.path.is_file()]


def _store_artifacts(
    storage: StorageBackend, run_id: str, specs: list[ArtifactSpec]
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for spec in specs:
        with spec.path.open("rb") as source:
            stored = storage.put(("runs", run_id, "artifacts"), spec.path.name, source)
        artifacts.append(
            {
                "artifact_type": spec.artifact_type,
                "title": spec.title,
                "relative_path": spec.path.name,
                "storage_uri": stored.uri,
                "mime_type": spec.mime_type,
                "size_bytes": stored.size_bytes,
                "sha256": stored.sha256,
                "display_order": spec.display_order,
            }
        )
    return artifacts


async def _mark_starting(settings: Settings, run_id: str) -> RunSnapshot:
    async with _worker_session(settings) as session:
        run = await session.get(Run, run_id)
        if run is None or run.dataset_id is None:
            raise RuntimeError(f"Validation run '{run_id}' does not exist.")
        if run.state != RunState.QUEUED.value:
            raise RuntimeError(f"Validation run '{run_id}' is in state {run.state}, not QUEUED.")
        run.state = RunState.STARTING.value
        run.started_at = datetime.now(UTC)
        await session.commit()
        return RunSnapshot(run.id, run.dataset_id, run.params_uri, run.profile, run.run_type)


async def _mark_running(settings: Settings, run_id: str, run_name: str) -> None:
    async with _worker_session(settings) as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise RuntimeError(f"Validation run '{run_id}' disappeared.")
        run.state = RunState.RUNNING.value
        run.nextflow_run_name = run_name
        await session.commit()


async def _mark_succeeded(
    settings: Settings,
    snapshot: RunSnapshot,
    artifacts: list[dict[str, Any]],
    *,
    dataset_status: str,
    session_id: str | None,
    bundle_summary: dict[str, Any] | None,
) -> None:
    async with _worker_session(settings) as session:
        run = await session.get(Run, snapshot.id)
        dataset = await session.get(Dataset, snapshot.dataset_id)
        if run is None or dataset is None:
            raise RuntimeError("Run or dataset disappeared before completion.")
        for item in artifacts:
            session.add(Artifact(run_id=run.id, metadata_json={}, **item))
        if bundle_summary is not None:
            artifact_by_type = {str(item["artifact_type"]): item for item in artifacts}
            archive = artifact_by_type["expression_bundle"]
            manifest = artifact_by_type["bundle_manifest"]
            prepared = PreparedDataset(
                id=str(bundle_summary["prepared_dataset_id"]),
                dataset_id=dataset.id,
                version=int(bundle_summary["prepared_version"]),
                preparation_run_id=run.id,
                bundle_uri=str(archive["storage_uri"]),
                bundle_manifest_uri=str(manifest["storage_uri"]),
                value_types_available=list(bundle_summary["value_types_available"]),
                sample_count=int(bundle_summary["sample_count"]),
                feature_count=int(bundle_summary["feature_count"]),
                qc_status=str(bundle_summary["qc_status"]),
            )
            session.add(prepared)
            await session.flush()
            run.prepared_dataset_id = prepared.id
        run.state = RunState.SUCCEEDED.value
        run.exit_code = 0
        run.nextflow_session_id = session_id
        run.finished_at = datetime.now(UTC)
        dataset.status = dataset_status
        await session.commit()


async def _mark_failed(
    settings: Settings, snapshot: RunSnapshot, previous_status: str, error: Exception
) -> None:
    async with _worker_session(settings) as session:
        run = await session.get(Run, snapshot.id)
        dataset = await session.get(Dataset, snapshot.dataset_id)
        if run is not None:
            run.state = RunState.FAILED.value
            run.exit_code = getattr(error, "returncode", None)
            run.error_summary = str(error)[:4000]
            run.finished_at = datetime.now(UTC)
        if dataset is not None:
            dataset.status = previous_status
        await session.commit()


def _session_id(log: str) -> str | None:
    match = SESSION_PATTERN.search(log)
    return match.group(1) if match else None


def _error_tail(value: str) -> str:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    return " | ".join(lines[-8:])[:2000]
