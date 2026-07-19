"""Worker task contract tests."""

from pathlib import Path

from transcriptforge_api.config import Settings
from transcriptforge_api.workers.analysis import _artifact_specs, _write_guidance_result
from transcriptforge_api.workers.assay_experiment import (
    _artifact_specs as _experiment_artifact_specs,
)
from transcriptforge_api.workers.assay_study import _artifact_specs as _study_artifact_specs
from transcriptforge_api.workers.celery_app import worker_health
from transcriptforge_api.workers.validation import RunSnapshot, build_nextflow_command


def test_worker_health_payload() -> None:
    assert worker_health.run() == {
        "status": "ok",
        "service": "transcriptforge-worker",
        "version": "0.1.0",
    }


def test_nextflow_command_is_an_argument_array(tmp_path: Path) -> None:
    settings = Settings(
        nextflow_executable="nextflow-test",
        pipeline_path=tmp_path / "main.nf",
    )
    snapshot = RunSnapshot("run-1", "dataset-1", "local://params.json", "test")
    command = build_nextflow_command(
        settings,
        snapshot,
        tmp_path / "params.json",
        tmp_path / "work",
        tmp_path / "provenance",
        "tf_run_1",
    )

    assert command[:4] == [
        "nextflow-test",
        "run",
        str((tmp_path / "main.nf").resolve()),
        "-entry",
    ]
    assert command[command.index("-profile") + 1] == "test"
    assert command[command.index("-params-file") + 1] == str(tmp_path / "params.json")


def test_awsbatch_command_uses_run_isolated_s3_work_prefix(tmp_path: Path) -> None:
    settings = Settings(
        nextflow_executable="nextflow-test",
        pipeline_path=tmp_path / "main.nf",
        aws_work_uri="s3://transcriptforge/work",
    )
    snapshot = RunSnapshot("run-1", "dataset-1", "local://params.json", "awsbatch")

    command = build_nextflow_command(
        settings,
        snapshot,
        tmp_path / "params.json",
        tmp_path / "local-work",
        tmp_path / "provenance",
        "tf_run_1",
    )

    assert command[command.index("-work-dir") + 1] == ("s3://transcriptforge/work/runs/run-1")


def test_signature_outputs_are_indexed_as_analysis_artifacts(tmp_path: Path) -> None:
    results = tmp_path / "output" / "analysis" / "results"
    results.mkdir(parents=True)
    for name in (
        "signature_scores.json",
        "signature_scores.tsv",
        "scored_features.tsv",
        "signature_scores.svg",
    ):
        (results / name).write_text("test\n", encoding="utf-8")

    artifacts = {item.artifact_type: item for item in _artifact_specs(tmp_path)}

    assert artifacts["signature_scores"].mime_type == "application/json"
    assert artifacts["signature_scores_table"].mime_type == "text/tab-separated-values"
    assert artifacts["signature_scored_features"].title == "Final scored signature features"
    assert artifacts["signature_scores_svg"].mime_type == "image/svg+xml"


def test_classifier_outputs_are_indexed_as_analysis_artifacts(tmp_path: Path) -> None:
    results = tmp_path / "output" / "analysis" / "results"
    results.mkdir(parents=True)
    for name in (
        "classifier_results.json",
        "oof_predictions.tsv",
        "feature_stability.tsv",
        "classifier_diagnostics.json",
        "classifier_diagnostics.svg",
        "model.json",
        "model_card.json",
        "model_card.md",
        "inference_schema.json",
        "inference_example.tsv",
    ):
        (results / name).write_text("test\n", encoding="utf-8")

    artifacts = {item.artifact_type: item for item in _artifact_specs(tmp_path)}

    assert artifacts["classifier_results"].mime_type == "application/json"
    assert artifacts["classifier_oof_predictions"].mime_type == "text/tab-separated-values"
    assert artifacts["classifier_feature_stability"].title == (
        "Feature stability across outer folds"
    )
    assert artifacts["classifier_diagnostics_svg"].mime_type == "image/svg+xml"
    assert artifacts["classifier_model"].title == "Locked elastic-net model"
    assert artifacts["classifier_model_card_markdown"].mime_type == "text/markdown"
    assert artifacts["classifier_inference_schema"].mime_type == "application/schema+json"


def test_development_evidence_download_inventory_is_indexed(tmp_path: Path) -> None:
    evidence = tmp_path / "output/experiment/results/development_evidence_bundle"
    expected = {
        "experiment_specification": ("experiment_spec.yaml", "application/yaml"),
        "experiment_question": ("question.json", "application/json"),
        "experiment_assignments": (
            "design/experiment_assignments.tsv",
            "text/tab-separated-values",
        ),
        "experiment_endpoint_parquet": (
            "endpoints/endpoint_table.parquet",
            "application/vnd.apache.parquet",
        ),
        "development_report_pdf": ("report/development_report.pdf", "application/pdf"),
        "experiment_input_checksums": (
            "provenance/input_checksums.tsv",
            "text/tab-separated-values",
        ),
    }
    for relative_path, _mime_type in expected.values():
        path = evidence / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test\n")

    artifacts = {item.artifact_type: item for item in _experiment_artifact_specs(tmp_path)}

    assert set(expected).issubset(artifacts)
    for artifact_type, (_relative_path, mime_type) in expected.items():
        assert artifacts[artifact_type].mime_type == mime_type


def test_validation_bundle_download_inventory_is_indexed(tmp_path: Path) -> None:
    evidence = tmp_path / "output/study/results/validation_bundle"
    expected = {
        "study_specification": ("study_spec.yaml", "application/yaml"),
        "locked_model_manifest": ("model_manifest.json", "application/json"),
        "study_assignments": (
            "design/study_assignments.tsv",
            "text/tab-separated-values",
        ),
        "study_endpoints_parquet": (
            "endpoints/endpoint_table.parquet",
            "application/vnd.apache.parquet",
        ),
        "variance_components": ("metrics/variance_components.json", "application/json"),
        "acceptance_results": ("metrics/acceptance_results.json", "application/json"),
        "validation_report_pdf": ("report/validation_report.pdf", "application/pdf"),
    }
    for relative_path, _mime_type in expected.values():
        path = evidence / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test\n")

    artifacts = {item.artifact_type: item for item in _study_artifact_specs(tmp_path)}

    assert set(expected).issubset(artifacts)
    for artifact_type, (_relative_path, mime_type) in expected.items():
        assert artifacts[artifact_type].mime_type == mime_type


def test_guided_analysis_emits_checksummed_source_evidence(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    (results / "result_manifest.json").write_text('{"schema_version":"1.0.0"}\n', encoding="utf-8")
    (results / "pca_plot.json").write_text('{"points":[]}\n', encoding="utf-8")
    frozen = {
        "analysis_id": "analysis-1",
        "run_id": "run-1",
        "analysis_type": "dimension_reduction",
        "guided_context": {
            "assay_project_id": "assay-1",
            "scientific_question_id": "question-1",
            "question_key": "largest_variance_source",
            "question": "What is the largest source of variation?",
            "formal_question": "Identify dominant biological and technical associations.",
        },
    }

    payload = _write_guidance_result(frozen, results)

    assert payload is not None
    assert payload["scientist_decision_required"] is True
    assert {item["artifact_type"] for item in payload["evidence_refs"]} == {
        "result_manifest",
        "pca_plot",
    }
    assert all(len(item["sha256"]) == 64 for item in payload["evidence_refs"])
    assert (results / "guidance_result.json").is_file()
