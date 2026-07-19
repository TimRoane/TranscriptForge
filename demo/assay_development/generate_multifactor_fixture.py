"""Generate a balanced constrained multifactor optimization smoke fixture."""

import argparse
import io
import json
import tarfile
from pathlib import Path


def generate(output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cells = [(method, input_ng) for method in ("method_a", "method_b") for input_ng in (50, 100)]
    measurements = [
        f"multi_{sample}_{method}_{input_ng}"
        for sample in range(1, 7)
        for method, input_ng in cells
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
                    str(
                        4
                        + feature * 0.1
                        + sample * 0.05
                        + (0.2 if method == "method_b" else 0)
                        + input_ng * 0.002
                        + (0.05 if method == "method_b" and input_ng == 100 else 0)
                    )
                    for sample in range(1, 7)
                    for method, input_ng in cells
                )
                for feature in range(1, 21)
            )
            + "\n"
        ).encode(),
        "expression_bundle/metadata/sample_metadata.tsv": (
            "sample_id\n" + "\n".join(measurements) + "\n"
        ).encode(),
    }
    bundle = output_dir / "expression_bundle.tar.gz"
    with tarfile.open(bundle, "w:gz") as archive:
        for name, content in sorted(bundle_files.items()):
            member = tarfile.TarInfo(name)
            member.size, member.mtime, member.mode = len(content), 0, 0o444
            archive.addfile(member, io.BytesIO(content))
    assignments = output_dir / "experiment_assignments.tsv"
    assignments.write_text(
        "measurement_id\tbiological_sample_id\tprepared_dataset_id\tinclude\t"
        "exclusion_reason\treplicate_id\tpair_id\tcondition\trun\toperator\t"
        "reagent_lot\tprocessing_order\textraction_method\tinput_ng\n"
        + "\n".join(
            f"multi_{sample}_{method}_{input_ng}\tmulti_{sample}\t"
            f"prepared-multifactor-smoke\ttrue\t\t{method}_{input_ng}\t"
            f"multi_{sample}\t{method}\trun_{1 + (sample + (input_ng == 100)) % 2}\t"
            f"operator_{1 + sample % 2}\tlot_{1 + sample % 2}\t"
            f"{(sample - 1) * 4 + index + 1}\t{method}\t{input_ng}"
            for sample in range(1, 7)
            for index, (method, input_ng) in enumerate(cells)
        )
        + "\n",
        encoding="utf-8",
    )
    spec = {
        "schema_version": "1.0.0",
        "experiment": {
            "experiment_id": "multifactor-smoke",
            "name": "Constrained multifactor smoke",
            "type": "MULTIFACTOR_OPTIMIZATION",
            "stage": "OPTIMIZE",
            "objective": "Estimate a bounded method by input design.",
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
            "question_key": "multifactor_optimization",
            "plain_language": "Which tested factor combinations merit confirmation?",
            "decision_to_inform": "Select prospective confirmation conditions.",
        },
        "inputs": {
            "assignment_table": "design/experiment_assignments.tsv",
            "expression_bundles": [
                {"prepared_dataset_id": "prepared-multifactor-smoke", "role": "development"}
            ],
        },
        "sample_structure": {
            "measurement_id": "measurement_id",
            "biological_sample_id": "biological_sample_id",
            "replicate_id": "replicate_id",
            "pair_id": "biological_sample_id",
        },
        "factors": [
            {"name": "extraction_method", "type": "categorical", "role": "primary"},
            {"name": "input_ng", "type": "continuous", "role": "primary"},
            {"name": "run", "type": "categorical", "role": "blocking"},
        ],
        "endpoints": {
            "primary": ["mean_expression", "fixed_effect_estimates"],
            "secondary": ["detected_genes", "variance_decomposition"],
        },
        "analysis_plan": {
            "template": "constrained_multifactor_optimization",
            "assay": "log_expression",
            "factor_names": ["extraction_method", "input_ng"],
            "interactions": ["extraction_method:input_ng"],
            "confidence_level": 0.95,
            "missing_value_policy": "fail_required_endpoint",
            "maximum_primary_factors": 3,
            "maximum_interactions": 2,
            "repeated_sample_model": "biological_sample_fixed_block_with_variance_summary",
            "response_surface_policy": "only_two_numeric_factors_with_supported_design",
        },
        "success_guidance": {
            "mode": "exploratory",
            "declared_questions": ["Which combinations merit prospective confirmation?"],
        },
        "rationales": {
            "factor_and_interaction_choice": "Method and input are plausible controllable effects.",
            "endpoint_choice": "Mean expression and variance summarize the synthetic endpoint.",
        },
    }
    spec_path = output_dir / "experiment_spec.json"
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    return {
        "experiment_spec": str(spec_path),
        "experiment_assignments": str(assignments),
        "expression_bundle": str(bundle),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    print(json.dumps(generate(parser.parse_args().output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
