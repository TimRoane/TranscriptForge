"""Generate a deterministic technical-feasibility Development Experiment fixture."""

import argparse
import io
import json
import tarfile
from pathlib import Path


def generate(output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    measurements = [f"feas_{sample}_{replicate}" for sample in range(1, 5) for replicate in (1, 2)]
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
                    str(5 + feature * 0.1 + sample * 0.03 + replicate * 0.01)
                    for sample in range(1, 5)
                    for replicate in (1, 2)
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
        "exclusion_reason\treplicate_id\tpair_id\tspecimen_group\tinput_ng\tdv200\t"
        "quality_metric\trun\toperator\treagent_lot\tprocessing_order\ttechnical_failure\n"
        + "\n".join(
            f"feas_{sample}_{replicate}\tfeas_{sample}\tprepared-feasibility-smoke\ttrue\t\t"
            f"replicate_{replicate}\tfeas_{sample}\t"
            f"{'FFPE' if sample <= 2 else 'fresh_frozen'}\t"
            f"{30 if sample <= 2 else 75}\t{45 + sample * 4}\t{7.1 + sample * 0.1}\t"
            f"run_{1 + (sample + replicate) % 2}\toperator_{replicate}\tlot_{replicate}\t"
            f"{(sample - 1) * 2 + replicate}\t"
            f"{'true' if sample == 1 and replicate == 2 else 'false'}"
            for sample in range(1, 5)
            for replicate in (1, 2)
        )
        + "\n",
        encoding="utf-8",
    )
    spec = {
        "schema_version": "1.0.0",
        "experiment": {
            "experiment_id": "technical-feasibility-smoke",
            "name": "Usable RNA technical feasibility smoke",
            "type": "TECHNICAL_FEASIBILITY",
            "stage": "FEASIBILITY",
            "objective": "Summarize technical usability across explicitly tested specimens.",
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
            "question_key": "usable_rna_feasibility",
            "plain_language": "Can usable RNA expression measurements be generated?",
            "decision_to_inform": "Choose whether feasibility work should continue.",
        },
        "inputs": {
            "assignment_table": "design/experiment_assignments.tsv",
            "expression_bundles": [
                {"prepared_dataset_id": "prepared-feasibility-smoke", "role": "development"}
            ],
        },
        "sample_structure": {
            "measurement_id": "measurement_id",
            "biological_sample_id": "biological_sample_id",
            "replicate_id": "replicate_id",
            "pair_id": "biological_sample_id",
        },
        "factors": [
            {"name": "specimen_group", "type": "categorical", "role": "primary"},
            {"name": "run", "type": "categorical", "role": "blocking"},
            {"name": "operator", "type": "categorical", "role": "blocking"},
        ],
        "endpoints": {
            "primary": ["technical_success_rate", "detected_genes"],
            "secondary": ["input_ng", "dv200", "failure_association_review"],
        },
        "analysis_plan": {
            "template": "technical_feasibility_summary",
            "assay": "log_expression",
            "confidence_level": 0.95,
            "missing_value_policy": "fail_required_endpoint",
            "failure_source": "explicit_assignment_or_nonfinite_expression",
            "criteria_mode": "exploratory",
        },
        "success_guidance": {
            "mode": "exploratory",
            "declared_questions": ["Do tested conditions merit further development?"],
        },
        "rationales": {
            "feasibility_scope": "Review usability without defining a specimen requirement.",
            "endpoint_choice": "Success and expression suitability describe feasibility.",
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
