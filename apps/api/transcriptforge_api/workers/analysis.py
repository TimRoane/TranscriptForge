"""Durable worker execution for saved analyses."""

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from transcriptforge_api.config import Settings, get_settings
from transcriptforge_api.models import (
    Analysis,
    Artifact,
    AssayAuditEvent,
    AssayDevelopmentProject,
    GuidanceResult,
    ModelRecord,
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
class AnalysisRunSnapshot:
    id: str
    analysis_id: str
    prepared_dataset_id: str
    params_uri: str
    profile: str


_SCHEMA_ROOT = Path(__file__).resolve().parents[4] / "schemas"
_GUIDANCE_SCHEMA = (
    Path(__file__).resolve().parents[4] / "contracts/guidance/guidance_result.schema.json"
)


def run_analysis_workflow(
    run_id: str,
    *,
    settings: Settings | None = None,
    storage: StorageBackend | None = None,
) -> dict[str, Any]:
    """Stage a frozen analysis request, launch Nextflow, and index its outputs."""
    settings = settings or get_settings()
    storage = storage or get_storage_backend()
    try:
        snapshot = asyncio.run(_mark_starting(settings, run_id))
    except RunCancelled:
        return {"run_id": run_id, "state": RunState.CANCELLED.value}
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
        deconvolution_results = result_manifest.parent / "deconvolution_results.json"
        if frozen.get("analysis_type") == "deconvolution":
            if not deconvolution_results.is_file():
                raise RuntimeError(
                    "Deconvolution analysis did not publish deconvolution_results.json."
                )
            _validate_json_contract(
                json.loads(deconvolution_results.read_text(encoding="utf-8")),
                "deconvolution_results.schema.json",
                "Deconvolution results",
            )
        classifier_results = result_manifest.parent / "classifier_results.json"
        classifier_registry: dict[str, Any] | None = None
        if frozen.get("analysis_type") == "classifier":
            if not classifier_results.is_file():
                raise RuntimeError("Classifier analysis did not publish classifier_results.json.")
            classifier_payload = json.loads(classifier_results.read_text(encoding="utf-8"))
            multiclass = frozen.get("method") == "multinomial_elastic_net"
            _validate_json_contract(
                classifier_payload,
                "multiclass_classifier_results.schema.json"
                if multiclass
                else "classifier_results.schema.json",
                "Classifier results",
            )
            locked_model = json.loads(
                (classifier_results.parent / "model.json").read_text(encoding="utf-8")
            )
            _validate_json_contract(
                locked_model,
                "multiclass_classifier_model.schema.json"
                if multiclass
                else "classifier_model.schema.json",
                "Locked model",
            )
            if multiclass:
                model_name = (
                    f"{classifier_payload['outcome']['column']} multinomial elastic-net classifier"
                )
                algorithm = "multinomial_elastic_net_logistic_regression"
            else:
                model_name = (
                    f"{classifier_payload['outcome']['positive_class']} versus "
                    f"{classifier_payload['outcome']['negative_class']} elastic-net classifier"
                )
                algorithm = "elastic_net_logistic_regression"
            classifier_registry = {
                "model_name": model_name,
                "algorithm": algorithm,
                "outcome_column": classifier_payload["outcome"]["column"],
                "metrics_json": {
                    "metrics": classifier_payload["metrics"],
                    "confidence_intervals": classifier_payload["confidence_intervals"],
                    "validation": "internal_grouped_repeated_nested_cross_validation",
                },
                "feature_count": len(locked_model["selected_feature_ids"]),
                "status": "CANDIDATE",
                "feature_schema_sha256": hashlib.sha256(
                    json.dumps(locked_model["selected_feature_ids"], separators=(",", ":")).encode()
                ).hexdigest(),
                "preprocessing_sha256": hashlib.sha256(
                    json.dumps(
                        locked_model["preprocessing"], sort_keys=True, separators=(",", ":")
                    ).encode()
                ).hexdigest(),
                "threshold_sha256": hashlib.sha256(
                    json.dumps(
                        _classifier_decision_rule(locked_model),
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
                "training_dataset_refs_json": [
                    {"prepared_dataset_id": locked_model["prepared_dataset_id"]}
                ],
                "validation_dataset_refs_json": [
                    {
                        "mode": "internal_grouped_repeated_nested_cross_validation",
                        "run_id": run_id,
                    }
                ],
                "container_digest": "sha256:"
                + hashlib.sha256(
                    json.dumps(
                        classifier_payload.get("software", {}),
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
            }
        guidance_payload = _write_guidance_result(frozen, result_manifest.parent)
        artifacts = _store_artifacts(storage, run_id, _artifact_specs(run_root))
        asyncio.run(
            _mark_succeeded(
                settings,
                snapshot,
                artifacts,
                session_id,
                classifier_registry,
                guidance_payload,
            )
        )
        return {"run_id": run_id, "state": RunState.SUCCEEDED.value}
    except RunCancelled as error:
        asyncio.run(_mark_cancelled(settings, snapshot, error))
        return {"run_id": run_id, "state": RunState.CANCELLED.value}
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


def _classifier_decision_rule(model: dict[str, Any]) -> dict[str, Any]:
    if model["model_type"] == "binary_elastic_net_logistic_regression":
        return {
            "operator": "gte",
            "threshold": model["decision_threshold"],
            "positive_class": model["positive_class"],
            "negative_class": model["negative_class"],
        }
    return {"operator": "argmax", "classes": model["classes"]}


def _write_guidance_result(frozen: dict[str, Any], results_dir: Path) -> dict[str, Any] | None:
    context = frozen.get("guided_context")
    if not isinstance(context, dict):
        return None
    analysis_type = str(frozen["analysis_type"])
    evidence_candidates: dict[str, list[tuple[str, str]]] = {
        "dimension_reduction": [
            ("pca_plot", "pca_plot.json"),
            ("embedding_plot", "embedding_plot.json"),
            ("dendrogram_plot", "dendrogram_plot.json"),
        ],
        "differential_expression": [
            ("differential_expression_results", "differential_expression.tsv"),
            ("method_diagnostics", "method_diagnostics.json"),
        ],
        "deconvolution": [("deconvolution_results", "deconvolution_results.json")],
        "signature": [("signature_scores", "signature_scores.json")],
        "classifier": [("classifier_results", "classifier_results.json")],
    }
    references: list[dict[str, str]] = []
    for artifact_type, relative_path in [
        ("result_manifest", "result_manifest.json"),
        *evidence_candidates.get(analysis_type, []),
    ]:
        path = results_dir / relative_path
        if path.is_file():
            references.append(
                {
                    "artifact_type": artifact_type,
                    "path": relative_path,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    labels = {
        "dimension_reduction": (
            "The guided variation analysis completed over the frozen expression measurements."
        ),
        "differential_expression": (
            "The guided differential-expression model completed with its frozen design and "
            "contrast."
        ),
        "deconvolution": (
            "The guided cell-composition analysis completed using the declared reference and "
            "assay semantics."
        ),
        "signature": (
            "The guided signature analysis completed using the frozen mapping and scoring method."
        ),
        "classifier": (
            "The leakage-resistant classifier development run completed with grouped nested "
            "validation."
        ),
    }
    risks = {
        "dimension_reduction": (
            "Observed component structure is associative and requires biological and technical "
            "metadata review."
        ),
        "differential_expression": (
            "Association does not establish causality; residual confounding and model sensitivity "
            "remain scientist-reviewed."
        ),
        "deconvolution": (
            "Reference mismatch and cell-state effects may influence estimates; inferred "
            "populations are not direct cell counts."
        ),
        "signature": (
            "Raw score magnitudes are not transferable across cohorts, platforms, or "
            "preprocessing pipelines."
        ),
        "classifier": (
            "Internal cross-validation is not independent external validation and does not "
            "establish clinical performance."
        ),
    }
    actions = {
        "dimension_reduction": (
            "Review component grouping against declared biological and technical variables."
        ),
        "differential_expression": (
            "Review effect direction, multiplicity, model diagnostics, and prespecified "
            "sensitivity analyses."
        ),
        "deconvolution": (
            "Review reference overlap and test whether composition is associated with the "
            "biological endpoint."
        ),
        "signature": (
            "Review mapping coverage and score association before selecting a candidate endpoint."
        ),
        "classifier": (
            "Review leakage audits, calibration, feature stability, and external-validation "
            "requirements before model review."
        ),
    }
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "assay_project_id": context["assay_project_id"],
        "scientific_question_id": context["scientific_question_id"],
        "analysis_id": frozen["analysis_id"],
        "run_id": frozen["run_id"],
        "analysis_type": analysis_type,
        "question_answered": context["question"],
        "important_findings": [labels[analysis_type]],
        "quality_warnings": [
            "This deterministic summary points to source artifacts; it does not replace "
            "scientist interpretation."
        ],
        "unresolved_risks": [risks[analysis_type]],
        "recommended_next_actions": [actions[analysis_type]],
        "evidence_refs": references,
        "scientist_decision_required": True,
    }
    schema = json.loads(_GUIDANCE_SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda item: tuple(str(part) for part in item.path),
    )
    if errors:
        raise RuntimeError(f"GuidanceResult violates its contract: {errors[0].message}")
    (results_dir / "guidance_result.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


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
            "guidance_result",
            "Question-aware guidance result",
            analysis / "guidance_result.json",
            "application/json",
            0,
        ),
        ArtifactSpec(
            "classifier_results",
            "Structured classifier results",
            analysis / "classifier_results.json",
            "application/json",
            1,
        ),
        ArtifactSpec(
            "classifier_oof_predictions",
            "Out-of-fold predictions",
            analysis / "oof_predictions.tsv",
            "text/tab-separated-values",
            2,
        ),
        ArtifactSpec(
            "classifier_feature_stability",
            "Feature stability across outer folds",
            analysis / "feature_stability.tsv",
            "text/tab-separated-values",
            3,
        ),
        ArtifactSpec(
            "classifier_diagnostics",
            "Classifier diagnostics",
            analysis / "classifier_diagnostics.json",
            "application/json",
            4,
        ),
        ArtifactSpec(
            "classifier_diagnostics_svg",
            "ROC, precision-recall, and learning curves",
            analysis / "classifier_diagnostics.svg",
            "image/svg+xml",
            5,
        ),
        ArtifactSpec(
            "classifier_model",
            "Locked elastic-net model",
            analysis / "model.json",
            "application/json",
            6,
        ),
        ArtifactSpec(
            "classifier_model_card",
            "Locked model card",
            analysis / "model_card.json",
            "application/json",
            7,
        ),
        ArtifactSpec(
            "classifier_model_card_markdown",
            "Locked model card (Markdown)",
            analysis / "model_card.md",
            "text/markdown",
            8,
        ),
        ArtifactSpec(
            "classifier_inference_schema",
            "Locked model inference schema",
            analysis / "inference_schema.json",
            "application/schema+json",
            9,
        ),
        ArtifactSpec(
            "classifier_inference_example",
            "Locked model inference template",
            analysis / "inference_example.tsv",
            "text/tab-separated-values",
            10,
        ),
        ArtifactSpec(
            "deconvolution_results",
            "Structured cell-population results",
            analysis / "deconvolution_results.json",
            "application/json",
            1,
        ),
        ArtifactSpec(
            "deconvolution_estimates",
            "Long-format cell-population estimates",
            analysis / "deconvolution_estimates.tsv",
            "text/tab-separated-values",
            2,
        ),
        ArtifactSpec(
            "deconvolution_reference_overlap",
            "Reference gene-overlap audit",
            analysis / "reference_overlap.tsv",
            "text/tab-separated-values",
            3,
        ),
        ArtifactSpec(
            "deconvolution_fractions_svg",
            "Estimated cell fractions (SVG)",
            analysis / "cell_fractions.svg",
            "image/svg+xml",
            4,
        ),
        ArtifactSpec(
            "deconvolution_enrichment_svg",
            "Cell-population enrichment patterns (SVG)",
            analysis / "enrichment_scores.svg",
            "image/svg+xml",
            4,
        ),
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
            "signature_associations_table",
            "Signature phenotype associations",
            analysis / "signature_associations.tsv",
            "text/tab-separated-values",
            5,
        ),
        ArtifactSpec(
            "signature_associations_svg",
            "Signature phenotype associations (SVG)",
            analysis / "signature_associations.svg",
            "image/svg+xml",
            6,
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
        if run.state in {RunState.CANCELLING.value, RunState.CANCELLED.value}:
            raise RunCancelled("Cancelled by user.")
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
        if run.state in {RunState.CANCELLING.value, RunState.CANCELLED.value}:
            raise RunCancelled("Cancelled by user.")
        run.state = RunState.RUNNING.value
        run.nextflow_run_name = run_name
        await session.commit()


async def _mark_succeeded(
    settings: Settings,
    snapshot: AnalysisRunSnapshot,
    artifacts: list[dict[str, Any]],
    session_id: str | None,
    classifier_registry: dict[str, Any] | None = None,
    guidance_payload: dict[str, Any] | None = None,
) -> None:
    async with _worker_session(settings) as session:
        run = await session.get(Run, snapshot.id)
        if run is None:
            raise RuntimeError("Analysis run disappeared before completion.")
        if run.state in {RunState.CANCELLING.value, RunState.CANCELLED.value}:
            raise RunCancelled("Cancelled by user.")
        for item in artifacts:
            session.add(Artifact(run_id=run.id, metadata_json={}, **item))
        if guidance_payload is not None:
            guidance_artifact = next(
                (item for item in artifacts if item["artifact_type"] == "guidance_result"),
                None,
            )
            analysis = await session.get(Analysis, snapshot.analysis_id)
            if guidance_artifact is None or analysis is None:
                raise RuntimeError("Guided analysis completed without a guidance artifact.")
            if (
                analysis.assay_project_id != guidance_payload["assay_project_id"]
                or analysis.scientific_question_id != guidance_payload["scientific_question_id"]
            ):
                raise RuntimeError("GuidanceResult lineage disagrees with the saved analysis.")
            session.add(
                GuidanceResult(
                    assay_project_id=guidance_payload["assay_project_id"],
                    question_id=guidance_payload["scientific_question_id"],
                    analysis_id=snapshot.analysis_id,
                    run_id=run.id,
                    payload_json=guidance_payload,
                    artifact_uri=guidance_artifact["storage_uri"],
                    artifact_sha256=guidance_artifact["sha256"],
                )
            )
            assay_project = await session.get(
                AssayDevelopmentProject, guidance_payload["assay_project_id"]
            )
            if assay_project is None:
                raise RuntimeError("Guided assay workspace disappeared before completion.")
            session.add(
                AssayAuditEvent(
                    assay_project_id=assay_project.id,
                    event_type="GUIDANCE_RESULT_CREATED",
                    actor="system",
                    object_type="GuidanceResult",
                    object_id=run.id,
                    hashes_json={"guidance_result": guidance_artifact["sha256"]},
                    details_json={
                        "analysis_id": snapshot.analysis_id,
                        "question_id": guidance_payload["scientific_question_id"],
                        "evidence_refs": guidance_payload["evidence_refs"],
                    },
                )
            )
        if classifier_registry is not None:
            artifact_by_type = {item["artifact_type"]: item for item in artifacts}
            model_artifact = artifact_by_type.get("classifier_model")
            card_artifact = artifact_by_type.get("classifier_model_card")
            if model_artifact is None or card_artifact is None:
                raise RuntimeError("Classifier completed without model registry artifacts.")
            session.add(
                ModelRecord(
                    analysis_id=snapshot.analysis_id,
                    run_id=run.id,
                    model_uri=model_artifact["storage_uri"],
                    model_card_uri=card_artifact["storage_uri"],
                    model_object_sha256=model_artifact["sha256"],
                    **classifier_registry,
                )
            )
        run.state = RunState.SUCCEEDED.value
        run.exit_code = 0
        run.nextflow_session_id = session_id
        run.finished_at = datetime.now(UTC)
        if guidance_payload is not None:
            from transcriptforge_api.services.guided_assay import recompute_guidance

            assert assay_project is not None
            await session.flush()
            await recompute_guidance(session, assay_project, commit=False)
        await session.commit()


async def _mark_cancelled(
    settings: Settings, snapshot: AnalysisRunSnapshot, error: RunCancelled
) -> None:
    async with _worker_session(settings) as session:
        run = await session.get(Run, snapshot.id)
        if run is not None:
            run.state = RunState.CANCELLED.value
            run.exit_code = 143
            run.error_summary = str(error)[:4000]
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
