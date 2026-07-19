"""Generate compact immutable inputs for the paired-condition Nextflow smoke test."""

import argparse
import io
import json
import tarfile
from pathlib import Path


def generate(output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    measurements = [
        f"pair_{sample}_{condition}"
        for sample in range(1, 5)
        for condition in ("method_a", "method_b")
    ]
    bundle_files = {
        "expression_bundle/bundle_manifest.json": json.dumps(
            {
                "assays": [{"name": "log_expression", "path": "assays/log_expression.tsv"}],
                "sample_metadata": "metadata/sample_metadata.tsv",
            }
        ).encode(),
        "expression_bundle/assays/log_expression.tsv": (
            "feature_id\t"
            + "\t".join(measurements)
            + "\n"
            + "\n".join(
                f"G{feature}\t"
                + "\t".join(
                    str(4 + feature * 0.2 + sample * 0.1 + (0.08 if condition == "method_b" else 0))
                    for sample in range(1, 5)
                    for condition in ("method_a", "method_b")
                )
                for feature in range(1, 21)
            )
            + "\n"
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

    assignments_path = output_dir / "experiment_assignments.tsv"
    assignments_path.write_text(
        "measurement_id\tbiological_sample_id\tprepared_dataset_id\tinclude\t"
        "exclusion_reason\treplicate_id\tpair_id\tcondition\trun\toperator\t"
        "reagent_lot\tquality_metric\tprocessing_order\n"
        + "\n".join(
            f"pair_{sample}_{condition}\tpair_{sample}\tprepared-paired-smoke\ttrue\t\t"
            f"{condition}\tpair_{sample}\t{condition}\trun_{1 + sample % 2}\t"
            f"operator_{1 + sample % 2}\tlot_{1 + sample % 2}\t{40 + sample * 10}\t"
            f"{(sample - 1) * 2 + (2 if condition == 'method_b' else 1)}"
            for sample in range(1, 5)
            for condition in ("method_a", "method_b")
        )
        + "\n",
        encoding="utf-8",
    )
    spec = {
        "schema_version": "1.0.0",
        "experiment": {
            "experiment_id": "paired-condition-smoke",
            "name": "Paired condition Nextflow smoke",
            "type": "PAIRED_CONDITION_COMPARISON",
            "stage": "OPTIMIZE",
            "objective": "Prove paired multi-endpoint workflow execution.",
            "exploratory": True,
            "mode": "ANALYZE_EXISTING",
            "revision": 1,
        },
        "assay_context": {
            "specimen_type": "synthetic_expression",
            "proposed_output": "expression_endpoint",
            "assay_version": "development-unlocked",
        },
        "question": {
            "question_key": "paired_condition_performance",
            "plain_language": "How do the paired methods compare?",
            "decision_to_inform": "Whether either method merits confirmation.",
        },
        "inputs": {
            "assignment_table": "design/experiment_assignments.tsv",
            "expression_bundles": [
                {"prepared_dataset_id": "prepared-paired-smoke", "role": "development"}
            ],
        },
        "sample_structure": {
            "measurement_id": "measurement_id",
            "biological_sample_id": "biological_sample_id",
            "replicate_id": "replicate_id",
            "pair_id": "biological_sample_id",
        },
        "factors": [
            {"name": "condition", "type": "categorical", "role": "primary"},
            {"name": "run", "type": "categorical", "role": "blocking"},
            {"name": "quality_metric", "type": "continuous", "role": "covariate"},
        ],
        "endpoints": {
            "primary": ["paired_mean_expression_difference", "expression_profile_correlation"],
            "secondary": ["failure_rate", "per_sample_discordance"],
        },
        "analysis_plan": {
            "template": "paired_condition_multi_endpoint_comparison",
            "assay": "log_expression",
            "reference_condition": "method_a",
            "comparator_condition": "method_b",
            "confidence_level": 0.95,
            "missing_value_policy": "fail_required_endpoint",
        },
        "success_guidance": {
            "mode": "exploratory",
            "declared_questions": ["Do complementary endpoints support confirmation?"],
        },
        "rationales": {
            "condition_contrast": "Method A is the current reference.",
            "endpoint_choice": "Bias, concordance, failures, and discordance are complementary.",
        },
    }
    spec_path = output_dir / "experiment_spec.json"
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "experiment_spec": str(spec_path),
        "experiment_assignments": str(assignments_path),
        "expression_bundle": str(bundle_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    print(json.dumps(generate(parser.parse_args().output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
