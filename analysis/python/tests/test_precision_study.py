"""Precision/reproducibility study and Validation Bundle acceptance tests."""

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from transcriptforge_analysis.precision_study import _evaluate_criteria, run_precision_study

ROOT = Path(__file__).parents[3]


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    measurement_ids = [f"bio_{sample}_{repeat}" for sample in range(1, 5) for repeat in (1, 2)]
    expression = [-2.05, -1.95, -1.05, -0.95, 0.95, 1.05, 1.95, 2.05]
    files = {
        "expression_bundle/bundle_manifest.json": json.dumps(
            {
                "assays": [{"name": "log_expression", "path": "assays/log_expression.tsv"}],
                "sample_metadata": "metadata/sample_metadata.tsv",
            }
        ).encode(),
        "expression_bundle/assays/log_expression.tsv": (
            "feature_id\t" + "\t".join(measurement_ids) + "\n"
            "G1\t" + "\t".join(str(value) for value in expression) + "\n"
            "G2\t" + "\t".join("0" for _ in expression) + "\n"
        ).encode(),
        "expression_bundle/metadata/sample_metadata.tsv": (
            "sample_id\n" + "\n".join(measurement_ids) + "\n"
        ).encode(),
    }
    bundle = tmp_path / "expression_bundle.tar.gz"
    with tarfile.open(bundle, "w:gz") as archive:
        for name, content in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            member.mtime = 0
            archive.addfile(member, io.BytesIO(content))
    model_payload = {
        "schema_version": "1.0.0",
        "model_type": "binary_elastic_net_logistic_regression",
        "analysis_id": "analysis-locked",
        "prepared_dataset_id": "development-bundle",
        "assay": "log_expression",
        "negative_class": "negative",
        "positive_class": "positive",
        "selected_feature_ids": ["G1"],
        "preprocessing": {"means": [0.0], "scales": [1.0]},
        "estimator": {"coefficients": [2.0], "intercept": 0.0},
        "calibration": {"method": "none", "coefficient": None, "intercept": None},
        "decision_threshold": 0.5,
    }
    model = tmp_path / "model.json"
    model.write_text(json.dumps(model_payload, sort_keys=True), encoding="utf-8")
    decision_rule = {
        "operator": "gte",
        "threshold": 0.5,
        "positive_class": "positive",
        "negative_class": "negative",
    }
    manifest_payload = {
        "schema_version": "1.0.0",
        "model_id": "model-locked",
        "status": "LOCKED",
        "ordered_feature_schema": ["G1"],
        "expected_assay": "log_expression",
        "serialized_model": {"sha256": hashlib.sha256(model.read_bytes()).hexdigest()},
        "container_digest": "sha256:" + "a" * 64,
        "checksums": {
            "feature_schema": hashlib.sha256(_canonical(["G1"])).hexdigest(),
            "preprocessing": hashlib.sha256(_canonical(model_payload["preprocessing"])).hexdigest(),
            "decision_rule": hashlib.sha256(_canonical(decision_rule)).hexdigest(),
        },
    }
    manifest = tmp_path / "model_manifest.json"
    manifest.write_text(json.dumps(manifest_payload, sort_keys=True), encoding="utf-8")
    assignments = tmp_path / "study_assignments.tsv"
    assignments.write_text(
        "measurement_id\tbiological_sample_id\treplicate_id\toperator\trun\tinclude\n"
        + "\n".join(
            f"{measurement}\tbio_{index // 2 + 1}\t{index % 2 + 1}\t"
            f"operator_{index % 2 + 1}\trun_{(index // 2) % 2 + 1}\ttrue"
            for index, measurement in enumerate(measurement_ids)
        )
        + "\n",
        encoding="utf-8",
    )
    spec_payload = {
        "schema_version": "1.0.0",
        "study": {
            "study_id": "study-precision",
            "name": "Deterministic precision study",
            "type": "PRECISION_REPRODUCIBILITY",
            "objective": "Quantify score and call reproducibility without retraining.",
            "revision": 1,
        },
        "assay_context": {
            "assay_name": "Synthetic locked assay",
            "assay_version": "1.0",
            "specimen_type": "synthetic expression",
            "intended_use_statement": "Research demonstration only.",
        },
        "model": {
            "model_id": "model-locked",
            "required_status": "LOCKED",
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        },
        "inputs": {
            "assignment_table": "design/study_assignments.tsv",
            "expression_bundles": [
                {"prepared_dataset_id": "validation-bundle", "role": "validation"}
            ],
        },
        "sample_structure": {
            "measurement_id": "measurement_id",
            "biological_sample_id": "biological_sample_id",
            "replicate_id": "replicate_id",
        },
        "factors": [
            {"name": "operator", "type": "categorical", "treatment": "random"},
            {"name": "run", "type": "categorical", "treatment": "random"},
        ],
        "endpoints": {
            "continuous": ["classifier_score"],
            "categorical": ["predicted_class"],
            "qc": [],
        },
        "analysis_plan": {
            "template": "crossed_random_effects",
            "confidence_level": 0.95,
            "bootstrap_iterations": 200,
            "threshold_proximity_band": 0.1,
        },
        "acceptance_criteria": [
            {
                "key": "score_icc",
                "metric": "icc",
                "endpoint": "classifier_score",
                "operator": "gte",
                "threshold": 0.9,
                "rationale": "Prespecified deterministic fixture criterion.",
            },
            {
                "key": "call_agreement",
                "metric": "categorical_agreement",
                "endpoint": "predicted_class",
                "operator": "gte",
                "threshold": 0.95,
                "rationale": "Prespecified deterministic fixture criterion.",
            },
        ],
        "design_validation": {"valid": True, "errors": [], "warnings": []},
    }
    spec_schema = json.loads((ROOT / "contracts/validation/study_spec.schema.json").read_text())
    Draft202012Validator(spec_schema).validate(spec_payload)
    spec = tmp_path / "study_spec.json"
    spec.write_text(json.dumps(spec_payload, sort_keys=True), encoding="utf-8")
    return bundle, model, manifest, spec, assignments


def test_precision_study_is_deterministic_and_never_retrains(tmp_path: Path) -> None:
    bundle, model, manifest, spec, assignments = _fixture(tmp_path)
    model_before = model.read_bytes()
    first = tmp_path / "first"
    second = tmp_path / "second"
    result = run_precision_study(bundle, model, manifest, spec, assignments, first)
    repeated = run_precision_study(bundle, model, manifest, spec, assignments, second)

    assert result == repeated
    assert result["overall_status"] == "PASS"
    assert result["metrics"]["variance_components"]["icc"] > 0.99
    assert result["metrics"]["agreement"]["categorical_agreement"] == 1.0
    assert model.read_bytes() == model_before
    assert (first / "validation_bundle.tar.gz").read_bytes() == (
        second / "validation_bundle.tar.gz"
    ).read_bytes()
    manifest_payload = json.loads(
        (first / "validation_bundle/manifest.json").read_text(encoding="utf-8")
    )
    schema = json.loads(
        (ROOT / "contracts/validation/validation_bundle_manifest.schema.json").read_text()
    )
    Draft202012Validator(schema).validate(manifest_payload)
    assert manifest_payload["model_retrained"] is False
    assert (first / "validation_bundle/endpoints/endpoint_table.parquet").is_file()
    assert (
        (first / "validation_bundle/report/validation_report.pdf").read_bytes().startswith(b"%PDF")
    )


def test_precision_study_rejects_manifest_checksum_before_endpoint_generation(
    tmp_path: Path,
) -> None:
    bundle, model, manifest, spec, assignments = _fixture(tmp_path)
    payload = json.loads(spec.read_text())
    payload["model"]["manifest_sha256"] = "0" * 64
    spec.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "invalid"

    with pytest.raises(ValueError, match="manifest checksum"):
        run_precision_study(bundle, model, manifest, spec, assignments, output)
    assert not (output / "validation_bundle/endpoints").exists()


def test_criteria_engine_preserves_fail_indeterminate_and_not_applicable() -> None:
    metrics = {
        "variance_components": {"icc": None},
        "agreement": {"categorical_agreement": 0.8},
        "precision": {"repeatability_sd": 0.2, "reproducibility_sd": 0.3},
    }
    results = _evaluate_criteria(
        [
            {
                "key": "failed",
                "metric": "categorical_agreement",
                "endpoint": "predicted_class",
                "operator": "gte",
                "threshold": 0.95,
                "rationale": "fixture",
            },
            {
                "key": "indeterminate",
                "metric": "icc",
                "endpoint": "classifier_score",
                "operator": "gte",
                "threshold": 0.9,
                "rationale": "fixture",
            },
            {
                "key": "not_applicable",
                "metric": "icc",
                "endpoint": "predicted_class",
                "operator": "gte",
                "threshold": 0.9,
                "rationale": "fixture",
            },
        ],
        metrics,
    )

    assert {item["key"]: item["status"] for item in results} == {
        "failed": "FAIL",
        "indeterminate": "INDETERMINATE",
        "not_applicable": "NOT_APPLICABLE",
    }
