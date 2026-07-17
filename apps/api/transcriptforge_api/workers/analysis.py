"""Durable worker execution for saved analyses."""

import asyncio
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from transcriptforge_api.config import Settings, get_settings
from transcriptforge_api.models import Artifact, Run
from transcriptforge_api.models.enums import RunState, RunType
from transcriptforge_api.storage import get_storage_backend
from transcriptforge_api.storage.base import StorageBackend
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
class AnalysisRunSnapshot:
    id: str
    analysis_id: str
    prepared_dataset_id: str
    params_uri: str
    profile: str


_SCHEMA_ROOT = Path(__file__).resolve().parents[4] / "schemas"


def run_analysis_workflow(
    run_id: str,
    *,
    settings: Settings | None = None,
    storage: StorageBackend | None = None,
) -> dict[str, Any]:
    """Stage a frozen analysis request, launch Nextflow, and index its outputs."""
    settings = settings or get_settings()
    storage = storage or get_storage_backend()
    snapshot = asyncio.run(_mark_starting(settings, run_id))
    try:
        frozen = json.loads(storage.read_bytes(snapshot.params_uri))
        _validate_json_contract(frozen, "analysis_request.schema.json", "Frozen analysis request")
        run_root = _confined_run_root(settings.run_work_root, run_id)
        input_dir = run_root / "input"
        output_dir = run_root / "output"
        work_dir = run_root / "work"
        provenance_dir = run_root / "provenance"
        for directory in (input_dir, output_dir, work_dir, provenance_dir):
            directory.mkdir(parents=True, exist_ok=True)

        bundle = _stage_bundle(storage, frozen["expression_bundle"], input_dir)
        request_path = input_dir / "analysis-request.json"
        request_path.write_text(
            json.dumps(frozen, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        launcher_params = input_dir / "nextflow-params.json"
        launcher_params.write_text(
            json.dumps(
                {
                    "analysis_request": str(request_path),
                    "expression_bundle": str(bundle),
                    "outdir": str(output_dir),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        run_name = f"tf_{run_id.replace('-', '_')}"
        command = _nextflow_command(
            settings, snapshot, launcher_params, work_dir, provenance_dir, run_name
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
                f"{_error_tail(completed.stdout or log_text or completed.stderr)}"
            )
        result_manifest = output_dir / "analysis" / "results" / "result_manifest.json"
        if not result_manifest.is_file():
            raise RuntimeError("Analysis completed without publishing result_manifest.json.")
        _validate_json_contract(
            json.loads(result_manifest.read_text(encoding="utf-8")),
            "result_manifest.schema.json",
            "Result manifest",
        )
        enrichment_requested = bool(
            frozen.get("parameters", {}).get("enrichment", {}).get("enabled", False)
        )
        enrichment_summary = result_manifest.parent / "enrichment_summary.json"
        if enrichment_requested and not enrichment_summary.is_file():
            raise RuntimeError(
                "Analysis requested enrichment but did not publish enrichment_summary.json."
            )
        if enrichment_summary.is_file():
            _validate_json_contract(
                json.loads(enrichment_summary.read_text(encoding="utf-8")),
                "enrichment_summary.schema.json",
                "Enrichment summary",
            )
        signature_scores = result_manifest.parent / "signature_scores.json"
        if frozen.get("analysis_type") == "signature":
            if not signature_scores.is_file():
                raise RuntimeError("Signature analysis did not publish signature_scores.json.")
            _validate_json_contract(
                json.loads(signature_scores.read_text(encoding="utf-8")),
                "signature_scores.schema.json",
                "Signature scores",
            )
        artifacts = _store_artifacts(storage, run_id, _artifact_specs(run_root))
        asyncio.run(_mark_succeeded(settings, snapshot, artifacts, session_id))
        return {"run_id": run_id, "state": RunState.SUCCEEDED.value}
    except Exception as error:
        asyncio.run(_mark_failed(settings, snapshot, error))
        raise


def _validate_json_contract(payload: Any, schema_name: str, label: str) -> None:
    schema_path = _SCHEMA_ROOT / schema_name
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda item: tuple(str(part) for part in item.path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "root"
        raise RuntimeError(f"{label} violates {schema_name} at {location}: {first.message}")


def _stage_bundle(storage: StorageBackend, item: dict[str, Any], input_dir: Path) -> Path:
    target = input_dir / "expression_bundle.tar.gz"
    temporary = target.with_name(f".{target.name}.tmp")
    digest = hashlib.sha256()
    with temporary.open("wb") as destination:
        storage.download(str(item["storage_uri"]), destination)
    with temporary.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != item["sha256"]:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("Staged Expression Bundle checksum does not match its frozen input.")
    temporary.replace(target)
    return target


def _nextflow_command(
    settings: Settings,
    snapshot: AnalysisRunSnapshot,
    params_path: Path,
    work_dir: Path,
    provenance_dir: Path,
    run_name: str,
) -> list[str]:
    effective_work_dir = _nextflow_work_dir(settings, snapshot.profile, snapshot.id, work_dir)
    return [
        settings.nextflow_executable,
        "run",
        str(settings.pipeline_path.resolve()),
        "-entry",
        "RUN_ANALYSIS",
        "-profile",
        snapshot.profile,
        "-params-file",
        str(params_path),
        "-work-dir",
        effective_work_dir,
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


def _artifact_specs(run_root: Path) -> list[ArtifactSpec]:
    analysis = run_root / "output" / "analysis" / "results"
    candidates = [
        ArtifactSpec(
            "signature_scores",
            "Per-sample signature scores",
            analysis / "signature_scores.json",
            "application/json",
            1,
        ),
        ArtifactSpec(
            "signature_scores_table",
            "Per-sample signature scores table",
            analysis / "signature_scores.tsv",
            "text/tab-separated-values",
            2,
        ),
        ArtifactSpec(
            "signature_scored_features",
            "Final scored signature features",
            analysis / "scored_features.tsv",
            "text/tab-separated-values",
            3,
        ),
        ArtifactSpec(
            "signature_scores_svg",
            "Per-sample signature scores (SVG)",
            analysis / "signature_scores.svg",
            "image/svg+xml",
            4,
        ),
        ArtifactSpec(
            "result_manifest",
            "Result manifest",
            analysis / "result_manifest.json",
            "application/json",
            0,
        ),
        ArtifactSpec(
            "differential_expression_results",
            "Complete differential-expression results",
            analysis / "differential_expression.tsv",
            "text/tab-separated-values",
            1,
        ),
        ArtifactSpec(
            "significant_results",
            "Significant differential-expression results",
            analysis / "significant_results.tsv",
            "text/tab-separated-values",
            2,
        ),
        ArtifactSpec(
            "normalized_expression",
            "Normalized expression profiles",
            analysis / "normalized_expression.tsv",
            "text/tab-separated-values",
            3,
        ),
        ArtifactSpec(
            "design_matrix",
            "Design matrix",
            analysis / "design_matrix.tsv",
            "text/tab-separated-values",
            4,
        ),
        ArtifactSpec(
            "contrast_definition",
            "Contrast definition",
            analysis / "contrast.json",
            "application/json",
            5,
        ),
        ArtifactSpec(
            "method_diagnostics",
            "Differential-expression method diagnostics",
            analysis / "method_diagnostics.json",
            "application/json",
            6,
        ),
        ArtifactSpec(
            "volcano_plot",
            "Volcano plot",
            analysis / "volcano_plot.json",
            "application/json",
            7,
        ),
        ArtifactSpec(
            "ma_plot",
            "MA plot",
            analysis / "ma_plot.json",
            "application/json",
            8,
        ),
        ArtifactSpec(
            "p_value_distribution",
            "P-value distribution",
            analysis / "p_value_distribution.json",
            "application/json",
            9,
        ),
        ArtifactSpec(
            "expression_heatmap",
            "Top-feature expression heatmap",
            analysis / "expression_heatmap.json",
            "application/json",
            10,
        ),
        ArtifactSpec(
            "volcano_plot_svg",
            "Volcano plot (SVG)",
            analysis / "volcano_plot.svg",
            "image/svg+xml",
            11,
        ),
        ArtifactSpec(
            "ma_plot_svg",
            "MA plot (SVG)",
            analysis / "ma_plot.svg",
            "image/svg+xml",
            12,
        ),
        ArtifactSpec(
            "p_value_distribution_svg",
            "P-value distribution (SVG)",
            analysis / "p_value_distribution.svg",
            "image/svg+xml",
            13,
        ),
        ArtifactSpec(
            "expression_heatmap_svg",
            "Top-feature expression heatmap (SVG)",
            analysis / "expression_heatmap.svg",
            "image/svg+xml",
            14,
        ),
        ArtifactSpec(
            "r_session_info",
            "R session information",
            analysis / "session_info.txt",
            "text/plain",
            15,
        ),
        ArtifactSpec(
            "enrichment_summary",
            "Gene-set enrichment summary",
            analysis / "enrichment_summary.json",
            "application/json",
            16,
        ),
        ArtifactSpec(
            "ranked_enrichment",
            "Ranked-list enrichment results",
            analysis / "ranked_enrichment.tsv",
            "text/tab-separated-values",
            17,
        ),
        ArtifactSpec(
            "over_representation",
            "Over-representation analysis results",
            analysis / "over_representation.tsv",
            "text/tab-separated-values",
            18,
        ),
        ArtifactSpec(
            "enrichment_plot_svg",
            "Gene-set enrichment overview",
            analysis / "enrichment_plot.svg",
            "image/svg+xml",
            19,
        ),
        ArtifactSpec(
            "pca_plot", "PCA coordinates plot", analysis / "pca_plot.json", "application/json", 1
        ),
        ArtifactSpec(
            "variance_plot",
            "Explained variance plot",
            analysis / "variance_plot.json",
            "application/json",
            2,
        ),
        ArtifactSpec(
            "pca_plot_svg",
            "PCA coordinates (SVG)",
            analysis / "pca_plot.svg",
            "image/svg+xml",
            2,
        ),
        ArtifactSpec(
            "variance_plot_svg",
            "Explained variance (SVG)",
            analysis / "variance_plot.svg",
            "image/svg+xml",
            3,
        ),
        ArtifactSpec(
            "embedding_plot",
            "Embedding plot",
            analysis / "embedding_plot.json",
            "application/json",
            1,
        ),
        ArtifactSpec(
            "embedding_plot_svg",
            "Embedding plot (SVG)",
            analysis / "embedding_plot.svg",
            "image/svg+xml",
            2,
        ),
        ArtifactSpec(
            "dendrogram_plot",
            "Sample dendrogram",
            analysis / "dendrogram_plot.json",
            "application/json",
            1,
        ),
        ArtifactSpec(
            "dendrogram_plot_svg",
            "Sample dendrogram (SVG)",
            analysis / "dendrogram_plot.svg",
            "image/svg+xml",
            2,
        ),
        ArtifactSpec(
            "correlation_heatmap",
            "Sample correlation heatmap",
            analysis / "correlation_heatmap.json",
            "application/json",
            2,
        ),
        ArtifactSpec(
            "correlation_heatmap_svg",
            "Sample correlation heatmap (SVG)",
            analysis / "correlation_heatmap.svg",
            "image/svg+xml",
            3,
        ),
        ArtifactSpec(
            "coordinates",
            "Sample coordinates",
            analysis / "coordinates.tsv",
            "text/tab-separated-values",
            3,
        ),
        ArtifactSpec(
            "pca_loadings",
            "PCA loadings",
            analysis / "loadings.tsv",
            "text/tab-separated-values",
            4,
        ),
        ArtifactSpec(
            "explained_variance",
            "Explained variance",
            analysis / "explained_variance.tsv",
            "text/tab-separated-values",
            5,
        ),
        ArtifactSpec(
            "cluster_assignments",
            "Cluster assignments",
            analysis / "cluster_assignments.tsv",
            "text/tab-separated-values",
            3,
        ),
        ArtifactSpec(
            "linkage_matrix",
            "Linkage matrix",
            analysis / "linkage_matrix.tsv",
            "text/tab-separated-values",
            4,
        ),
        ArtifactSpec(
            "analysis_report", "Analysis report", analysis / "report.html", "text/html", 6
        ),
        ArtifactSpec(
            "analysis_report_source",
            "Quarto report source",
            analysis / "report.qmd",
            "text/markdown",
            7,
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
            "nextflow_dag", "Execution DAG", run_root / "provenance/dag.html", "text/html", 23
        ),
    ]
    return [item for item in candidates if item.path.is_file()]


async def _mark_starting(settings: Settings, run_id: str) -> AnalysisRunSnapshot:
    async with _worker_session(settings) as session:
        run = await session.get(Run, run_id)
        if (
            run is None
            or run.analysis_id is None
            or run.prepared_dataset_id is None
            or run.run_type != RunType.ANALYSIS.value
        ):
            raise RuntimeError(f"Analysis run '{run_id}' does not exist.")
        if run.state != RunState.QUEUED.value:
            raise RuntimeError(f"Analysis run '{run_id}' is in state {run.state}, not QUEUED.")
        run.state = RunState.STARTING.value
        run.started_at = datetime.now(UTC)
        await session.commit()
        return AnalysisRunSnapshot(
            run.id, run.analysis_id, run.prepared_dataset_id, run.params_uri, run.profile
        )


async def _mark_running(settings: Settings, run_id: str, run_name: str) -> None:
    async with _worker_session(settings) as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise RuntimeError(f"Analysis run '{run_id}' disappeared.")
        run.state = RunState.RUNNING.value
        run.nextflow_run_name = run_name
        await session.commit()


async def _mark_succeeded(
    settings: Settings,
    snapshot: AnalysisRunSnapshot,
    artifacts: list[dict[str, Any]],
    session_id: str | None,
) -> None:
    async with _worker_session(settings) as session:
        run = await session.get(Run, snapshot.id)
        if run is None:
            raise RuntimeError("Analysis run disappeared before completion.")
        for item in artifacts:
            session.add(Artifact(run_id=run.id, metadata_json={}, **item))
        run.state = RunState.SUCCEEDED.value
        run.exit_code = 0
        run.nextflow_session_id = session_id
        run.finished_at = datetime.now(UTC)
        await session.commit()


async def _mark_failed(settings: Settings, snapshot: AnalysisRunSnapshot, error: Exception) -> None:
    async with _worker_session(settings) as session:
        run = await session.get(Run, snapshot.id)
        if run is not None:
            run.state = RunState.FAILED.value
            run.exit_code = getattr(error, "returncode", None)
            run.error_summary = str(error)[:4000]
            run.finished_at = datetime.now(UTC)
        await session.commit()
