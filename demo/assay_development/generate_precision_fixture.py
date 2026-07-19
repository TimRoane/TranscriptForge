"""Generate compact immutable inputs for the RUN_ASSAY_STUDY smoke test."""

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
    measurement_ids = [
        f"precision_{sample}_{repeat}" for sample in range(1, 5) for repeat in (1, 2)
    ]
    values = [-2.05, -1.95, -1.05, -0.95, 0.95, 1.05, 1.95, 2.05]
    bundle_files = {
        "expression_bundle/bundle_manifest.json": json.dumps(
            {
                "assays": [{"name": "log_expression", "path": "assays/log_expression.tsv"}],
                "sample_metadata": "metadata/sample_metadata.tsv",
            }
        ).encode(),
        "expression_bundle/assays/log_expression.tsv": (
            "feature_id\t" + "\t".join(measurement_ids) + "\n"
            "G1\t" + "\t".join(str(value) for value in values) + "\n"
            "G2\t" + "\t".join("0" for _ in values) + "\n"
        ).encode(),
        "expression_bundle/metadata/sample_metadata.tsv": (
            "sample_id\n" + "\n".join(measurement_ids) + "\n"
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
        "analysis_id": "smoke-analysis",
        "prepared_dataset_id": "smoke-development-bundle",
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
        "model_id": "smoke-model-locked",
        "status": "LOCKED",
        "ordered_feature_schema": ["G1"],
        "expected_assay": "log_expression",
        "serialized_model": {"sha256": hashlib.sha256(model_path.read_bytes()).hexdigest()},
        "container_digest": "sha256:" + "a" * 64,
        "checksums": {
            "feature_schema": hashlib.sha256(_canonical(["G1"])).hexdigest(),
            "preprocessing": hashlib.sha256(_canonical(model["preprocessing"])).hexdigest(),
            "decision_rule": hashlib.sha256(_canonical(decision_rule)).hexdigest(),
        },
    }
    manifest_path = output_dir / "model_manifest.json"
    _write_json(manifest_path, manifest)

    assignment_path = output_dir / "study_assignments.tsv"
    assignment_path.write_text(
        "measurement_id\tbiological_sample_id\treplicate_id\toperator\trun\tinclude\n"
        + "\n".join(
            f"{measurement}\tprecision_{index // 2 + 1}\t{index % 2 + 1}\t"
            f"operator_{index % 2 + 1}\trun_{(index // 2) % 2 + 1}\ttrue"
            for index, measurement in enumerate(measurement_ids)
        )
        + "\n",
        encoding="utf-8",
    )
    spec = {
        "schema_version": "1.0.0",
        "study": {
            "study_id": "smoke-precision-study",
            "name": "Nextflow precision smoke study",
            "type": "PRECISION_REPRODUCIBILITY",
            "objective": "Prove deterministic locked-model precision execution.",
            "revision": 1,
        },
        "assay_context": {
            "assay_name": "Synthetic smoke assay",
            "assay_version": "1.0",
            "specimen_type": "synthetic expression",
            "intended_use_statement": "Workflow smoke test only.",
        },
        "model": {
            "model_id": "smoke-model-locked",
            "required_status": "LOCKED",
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        },
        "inputs": {
            "assignment_table": "design/study_assignments.tsv",
            "expression_bundles": [
                {"prepared_dataset_id": "smoke-validation", "role": "validation"}
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
                "rationale": "Prespecified deterministic workflow-smoke threshold.",
            },
            {
                "key": "call_agreement",
                "metric": "categorical_agreement",
                "endpoint": "predicted_class",
                "operator": "gte",
                "threshold": 0.95,
                "rationale": "Prespecified deterministic workflow-smoke threshold.",
            },
        ],
        "design_validation": {"valid": True, "errors": [], "warnings": []},
    }
    spec_path = output_dir / "study_spec.json"
    _write_json(spec_path, spec)
    return {
        "study_spec": str(spec_path),
        "study_assignments": str(assignment_path),
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
