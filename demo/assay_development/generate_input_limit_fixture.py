"""Generate deterministic inputs for the locked-model input-limit workflow smoke test."""

import argparse
import hashlib
import io
import json
import tarfile
from pathlib import Path
from typing import Any


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generate(output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    levels = (100, 50, 25)
    measurements = [
        f"limit_{sample}_{level}" for sample in range(1, 5) for level in levels
    ]
    baselines = (-1.5, -0.5, 0.5, 1.5)
    values = [
        baselines[sample - 1] - {100: 0.0, 50: 0.02, 25: 0.04}[level]
        for sample in range(1, 5)
        for level in levels
    ]
    bundle_files = {
        "expression_bundle/bundle_manifest.json": json.dumps(
            {
                "assays": [{"name": "log_expression", "path": "assays/log_expression.tsv"}],
                "sample_metadata": "metadata/sample_metadata.tsv",
            }
        ).encode(),
        "expression_bundle/assays/log_expression.tsv": (
            "feature_id\t" + "\t".join(measurements) + "\n"
            "G1\t" + "\t".join(str(value) for value in values) + "\n"
            "G2\t" + "\t".join("0" for _ in values) + "\n"
        ).encode(),
        "expression_bundle/metadata/sample_metadata.tsv": (
            "sample_id\n" + "\n".join(measurements) + "\n"
        ).encode(),
    }
    bundle_path = output_dir / "expression_bundle.tar.gz"
    with tarfile.open(bundle_path, "w:gz") as archive:
        for name, content in sorted(bundle_files.items()):
            member = tarfile.TarInfo(name)
            member.size = len(content)
            member.mtime = 0
            member.mode = 0o444
            archive.addfile(member, io.BytesIO(content))

    model = {
        "schema_version": "1.0.0",
        "model_type": "binary_elastic_net_logistic_regression",
        "analysis_id": "limit-smoke-analysis",
        "prepared_dataset_id": "limit-development-bundle",
        "assay": "log_expression",
        "negative_class": "negative",
        "positive_class": "positive",
        "selected_feature_ids": ["G1"],
        "preprocessing": {"means": [0.0], "scales": [1.0]},
        "estimator": {"coefficients": [2.0], "intercept": 0.0},
        "calibration": {"method": "none", "coefficient": None, "intercept": None},
        "decision_threshold": 0.5,
    }
    model_path = output_dir / "model.json"
    _write_json(model_path, model)
    decision_rule = {
        "operator": "gte",
        "threshold": 0.5,
        "positive_class": "positive",
        "negative_class": "negative",
    }
    manifest = {
        "schema_version": "1.0.0",
        "model_id": "limit-smoke-model",
        "status": "LOCKED",
        "ordered_feature_schema": ["G1"],
        "expected_assay": "log_expression",
        "serialized_model": {"sha256": hashlib.sha256(model_path.read_bytes()).hexdigest()},
        "container_digest": "sha256:" + "b" * 64,
        "checksums": {
            "feature_schema": hashlib.sha256(_canonical(["G1"])).hexdigest(),
            "preprocessing": hashlib.sha256(_canonical(model["preprocessing"])).hexdigest(),
            "decision_rule": hashlib.sha256(_canonical(decision_rule)).hexdigest(),
        },
    }
    manifest_path = output_dir / "model_manifest.json"
    _write_json(manifest_path, manifest)

    assignments_path = output_dir / "study_assignments.tsv"
    assignments_path.write_text(
        "measurement_id\tbiological_sample_id\treplicate_id\toperator\trun\t"
        "reagent_lot\tinput_level\tquality_metric\tqc_failure\tinclude\n"
        + "\n".join(
            f"limit_{sample}_{level}\tlimit_{sample}\t{level}\toperator_{1 + sample % 2}\t"
            f"run_{1 + sample % 2}\tlot_{1 + sample % 2}\t{level}\t"
            f"{40 + level / 2 + sample}\tfalse\ttrue"
            for sample in range(1, 5)
            for level in levels
        )
        + "\n",
        encoding="utf-8",
    )
    spec = {
        "schema_version": "1.0.0",
        "study": {
            "study_id": "input-limit-smoke-study",
            "name": "Input limit workflow smoke study",
            "type": "INPUT_DEGRADATION_LIMIT",
            "objective": "Evaluate a locked endpoint across paired ordered input levels.",
            "revision": 1,
        },
        "assay_context": {
            "assay_name": "Synthetic locked endpoint",
            "assay_version": "1.0",
            "specimen_type": "synthetic expression",
            "intended_use_statement": "Workflow smoke test only.",
        },
        "model": {
            "model_id": "limit-smoke-model",
            "required_status": "LOCKED",
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        },
        "inputs": {
            "assignment_table": "design/study_assignments.tsv",
            "expression_bundles": [
                {"prepared_dataset_id": "limit-validation", "role": "validation"}
            ],
        },
        "sample_structure": {
            "measurement_id": "measurement_id",
            "biological_sample_id": "biological_sample_id",
            "replicate_id": "replicate_id",
        },
        "factors": [
            {"name": "input_level", "type": "ordered_numeric", "treatment": "fixed"},
            {"name": "quality_metric", "type": "continuous", "treatment": "fixed"},
            {"name": "run", "type": "categorical", "treatment": "random"},
        ],
        "endpoints": {
            "continuous": ["classifier_score", "score_difference_from_reference"],
            "categorical": ["predicted_class", "call_agreement_to_reference"],
            "qc": ["qc_failure"],
        },
        "analysis_plan": {
            "template": "ordered_level_locked_endpoint_limit",
            "reference_level": 100,
            "confidence_level": 0.95,
            "bootstrap_iterations": 200,
            "threshold_proximity_band": 0.1,
            "level_rationale": "The highest tested level is the reference.",
        },
        "acceptance_criteria": [
            {
                "key": "score_stability_all_levels",
                "metric": "mean_absolute_score_difference",
                "endpoint": "classifier_score",
                "operator": "all_levels",
                "threshold": 0.1,
                "rationale": "Maximum paired score change at every lower level.",
            },
            {
                "key": "call_stability_consecutive",
                "metric": "call_agreement_to_reference",
                "endpoint": "predicted_class",
                "operator": "consecutive_levels",
                "threshold": 0.95,
                "rationale": "Call stability through consecutive lower levels.",
            },
            {
                "key": "qc_failure_all_levels",
                "metric": "qc_failure_rate",
                "endpoint": "qc_failure",
                "operator": "all_levels",
                "threshold": 0.1,
                "rationale": "Maximum failure rate at every lower level.",
            },
        ],
        "design_validation": {"valid": True, "errors": [], "warnings": []},
    }
    spec_path = output_dir / "study_spec.json"
    _write_json(spec_path, spec)
    return {
        "study_spec": str(spec_path),
        "study_assignments": str(assignments_path),
        "expression_bundle": str(bundle_path),
        "model": str(model_path),
        "model_manifest": str(manifest_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    print(json.dumps(generate(parser.parse_args().output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
