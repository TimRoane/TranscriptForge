"""Generate deterministic inputs for the locked-model paired-bridging smoke test."""

import argparse
import hashlib
import io
import json
import tarfile
from pathlib import Path

try:
    from demo.assay_development.generate_input_limit_fixture import generate as generate_model
except ModuleNotFoundError:  # Direct script execution places this directory on sys.path.
    from generate_input_limit_fixture import (
        generate as generate_model,  # type: ignore[import-not-found,no-redef]
    )


def generate(output_dir: Path) -> dict[str, str]:
    base = generate_model(output_dir)
    measurements = [
        f"bridge_{sample}_{condition}"
        for sample in range(1, 7)
        for condition in ("pipeline_a", "pipeline_b")
    ]
    baselines = (-1.4, -0.8, -0.3, 0.3, 0.8, 1.4)
    values = [
        baselines[sample - 1] + (0.015 if condition == "pipeline_b" else 0.0)
        for sample in range(1, 7)
        for condition in ("pipeline_a", "pipeline_b")
    ]
    files = {
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
    bundle_path = Path(base["expression_bundle"])
    with tarfile.open(bundle_path, "w:gz") as archive:
        for name, content in sorted(files.items()):
            member = tarfile.TarInfo(name)
            member.size = len(content)
            member.mtime = 0
            member.mode = 0o444
            archive.addfile(member, io.BytesIO(content))
    assignments = output_dir / "study_assignments.tsv"
    assignments.write_text(
        "measurement_id\tbiological_sample_id\treplicate_id\toperator\trun\t"
        "reagent_lot\tcondition\tsubgroup\tinclude\n"
        + "\n".join(
            f"bridge_{sample}_{condition}\tbridge_{sample}\t{condition}\t"
            f"operator_{1 + sample % 2}\trun_{1 + sample % 2}\tlot_{1 + sample % 2}\t"
            f"{condition}\t{'low_quality' if sample <= 3 else 'high_quality'}\ttrue"
            for sample in range(1, 7)
            for condition in ("pipeline_a", "pipeline_b")
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_sha = hashlib.sha256(Path(base["model_manifest"]).read_bytes()).hexdigest()
    spec = {
        "schema_version": "1.0.0",
        "study": {
            "study_id": "paired-bridge-smoke-study",
            "name": "Paired bridge workflow smoke study",
            "type": "PAIRED_BRIDGING",
            "objective": "Evaluate a candidate pipeline change against the locked reference.",
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
            "manifest_sha256": manifest_sha,
        },
        "inputs": {
            "assignment_table": "design/study_assignments.tsv",
            "expression_bundles": [
                {"prepared_dataset_id": "bridge-validation", "role": "validation"}
            ],
        },
        "sample_structure": {
            "measurement_id": "measurement_id",
            "biological_sample_id": "biological_sample_id",
            "replicate_id": "replicate_id",
        },
        "factors": [
            {"name": "condition", "type": "categorical", "treatment": "fixed"},
            {"name": "run", "type": "categorical", "treatment": "random"},
            {"name": "subgroup", "type": "categorical", "treatment": "fixed"},
        ],
        "endpoints": {
            "continuous": ["classifier_score", "paired_bias"],
            "categorical": ["predicted_class", "categorical_agreement"],
            "qc": [],
        },
        "analysis_plan": {
            "template": "paired_locked_endpoint_bridging",
            "reference_condition": "pipeline_a",
            "comparator_condition": "pipeline_b",
            "equivalence_margin": 0.05,
            "condition_rationale": "Pipeline A is the locked reference.",
            "confidence_level": 0.95,
            "bootstrap_iterations": 200,
            "threshold_proximity_band": 0.1,
            "correlation_passes_equivalence": False,
        },
        "acceptance_criteria": [
            {
                "key": "paired_bias_margin",
                "metric": "paired_bias",
                "endpoint": "classifier_score",
                "operator": "absolute_lte",
                "threshold": 0.05,
                "rationale": "Absolute paired score bias must remain within margin.",
            },
            {
                "key": "call_agreement",
                "metric": "categorical_agreement",
                "endpoint": "predicted_class",
                "operator": "gte",
                "threshold": 0.95,
                "rationale": "Categorical calls must remain concordant.",
            },
            {
                "key": "tost_equivalence",
                "metric": "tost_equivalence",
                "endpoint": "classifier_score",
                "operator": "gte",
                "threshold": 1,
                "rationale": "The paired confidence interval must lie within margin.",
            },
        ],
        "design_validation": {"valid": True, "errors": [], "warnings": []},
    }
    spec_path = output_dir / "study_spec.json"
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "study_spec": str(spec_path),
        "study_assignments": str(assignments),
        "expression_bundle": str(bundle_path),
        "model": base["model"],
        "model_manifest": base["model_manifest"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    print(json.dumps(generate(parser.parse_args().output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
