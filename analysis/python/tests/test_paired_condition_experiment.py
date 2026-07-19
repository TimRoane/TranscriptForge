"""Scientific acceptance tests for paired-condition Development Experiments."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from transcriptforge_analysis.assay_experiment import (
    run_paired_condition_experiment,
    validate_paired_condition_design,
)
from transcriptforge_analysis.expression_bundle import BundleConfig, build_expression_bundle
from transcriptforge_analysis.matrix_validation import ValidationConfig


def _spec() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "experiment": {
            "experiment_id": "exp-paired-method",
            "name": "Paired library-method comparison",
            "type": "PAIRED_CONDITION_COMPARISON",
            "stage": "OPTIMIZE",
            "objective": "Compare two library conditions across the same specimens.",
            "exploratory": True,
            "mode": "ANALYZE_EXISTING",
            "revision": 1,
        },
        "assay_context": {
            "specimen_type": "simulated_ffpe",
            "proposed_output": "expression_endpoint",
            "assay_version": "development-unlocked",
        },
        "question": {
            "question_key": "paired_condition_performance",
            "plain_language": "How do the paired library conditions compare?",
            "decision_to_inform": "Whether either condition merits confirmation.",
        },
        "inputs": {
            "assignment_table": "design/experiment_assignments.tsv",
            "expression_bundles": [
                {"prepared_dataset_id": "prepared-paired", "role": "development"}
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
            "primary": ["paired_mean_expression_difference", "profile_correlation"],
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
            "declared_questions": ["Are paired profiles concordant without systematic bias?"],
        },
        "rationales": {
            "condition_contrast": "Method A is the current process reference.",
            "endpoint_choice": "Bias, concordance, failures, and discordance are complementary.",
        },
    }


def _rows() -> list[dict[str, str]]:
    rows = []
    for sample_index in range(1, 5):
        for condition in ("method_a", "method_b"):
            rows.append(
                {
                    "measurement_id": f"bio_{sample_index}_{condition}",
                    "biological_sample_id": f"bio_{sample_index}",
                    "prepared_dataset_id": "prepared-paired",
                    "include": "true",
                    "exclusion_reason": "",
                    "replicate_id": condition,
                    "pair_id": f"bio_{sample_index}",
                    "condition": condition,
                    "run": f"run_{1 + sample_index % 2}",
                    "operator": f"operator_{1 + sample_index % 2}",
                    "reagent_lot": f"lot_{1 + sample_index % 2}",
                    "quality_metric": str(45 + sample_index * 10),
                    "processing_order": str((sample_index - 1) * 2 + (condition == "method_b") + 1),
                }
            )
    return rows


def _write_assignments(path: Path, rows: list[dict[str, str]]) -> None:
    columns = list(rows[0])
    path.write_text(
        "\t".join(columns)
        + "\n"
        + "".join("\t".join(row[column] for column in columns) + "\n" for row in rows),
        encoding="utf-8",
    )


def _bundle(tmp_path: Path) -> Path:
    rows = _rows()
    samples = [row["measurement_id"] for row in rows]
    matrix = tmp_path / "matrix.tsv"
    metadata = tmp_path / "metadata.tsv"
    matrix.write_text(
        "feature_id\t"
        + "\t".join(samples)
        + "\n"
        + "\n".join(
            "\t".join(
                [
                    f"ENSG{feature:011d}",
                    *[
                        str(
                            100
                            + feature * 9
                            + (sample_index // 2) * 3
                            + (4 if sample_index % 2 else 0)
                            + (sample_index % 2) * (feature % 3)
                        )
                        for sample_index in range(len(samples))
                    ],
                ]
            )
            for feature in range(1, 17)
        )
        + "\n",
        encoding="utf-8",
    )
    metadata.write_text(
        "sample_id\tcondition\n"
        + "".join(f"{row['measurement_id']}\t{row['condition']}\n" for row in rows),
        encoding="utf-8",
    )
    output = tmp_path / "bundle"
    build_expression_bundle(
        BundleConfig(
            validation=ValidationConfig(
                dataset_id="dataset-paired",
                name="Paired method fixture",
                matrix_path=matrix,
                metadata_path=metadata,
                matrix_orientation="features_by_samples",
                feature_id_column="feature_id",
                sample_id_column="sample_id",
                value_type="raw_counts",
            ),
            prepared_dataset_id="prepared-paired",
            prepared_version=1,
        ),
        output,
    )
    return output / "expression_bundle.tar.gz"


def test_paired_design_blocks_missing_pairs_and_condition_run_confounding() -> None:
    missing = _rows()[:-1]
    result = validate_paired_condition_design(_spec(), missing)
    assert result.valid is False
    assert "DESIGN.PAIRED_CONDITIONS_INCOMPLETE" in {item.code for item in result.findings}

    confounded = _rows()
    for row in confounded:
        row["run"] = f"run_{row['condition']}"
    result = validate_paired_condition_design(_spec(), confounded)
    assert result.valid is False
    assert "DESIGN.CONDITION_RUN_CONFOUNDED" in {item.code for item in result.findings}


def test_paired_condition_bundle_is_deterministic_and_contract_valid(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.json"
    assignments_path = tmp_path / "assignments.tsv"
    spec_path.write_text(json.dumps(_spec(), indent=2), encoding="utf-8")
    _write_assignments(assignments_path, _rows())
    archive = _bundle(tmp_path)

    first = tmp_path / "first"
    second = tmp_path / "second"
    first_manifest = run_paired_condition_experiment(
        spec_path, assignments_path, archive, first
    )
    second_manifest = run_paired_condition_experiment(
        spec_path, assignments_path, archive, second
    )
    assert first_manifest == second_manifest
    first_bundle = first / "development_evidence_bundle"
    second_bundle = second / "development_evidence_bundle"
    for relative in (
        "manifest.json",
        "design/design_validation.json",
        "endpoints/endpoint_table.parquet",
        "results/primary_results.json",
        "results/paired_differences.tsv",
        "figures/bland_altman.svg",
        "decision/decision_summary.json",
        "report/development_report.html",
    ):
        assert (first_bundle / relative).read_bytes() == (second_bundle / relative).read_bytes()

    root = Path(__file__).parents[3]
    manifest_schema = json.loads(
        (root / "contracts/experiment/development_evidence_manifest.schema.json").read_text()
    )
    decision_schema = json.loads(
        (root / "contracts/experiment/decision_summary.schema.json").read_text()
    )
    Draft202012Validator(manifest_schema).validate(first_manifest)
    summary = json.loads(
        (first_bundle / "decision/decision_summary.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(decision_schema).validate(summary)
    comparison = summary["condition_results"][0]
    assert comparison["pair_count"] == 4
    assert comparison["mean_paired_difference"] > 0
    assert comparison["mean_profile_correlation"] > 0.99
    assert comparison["condition_by_quality_interaction"]["status"] == "ESTIMATED"
    assert any("one metric" in limitation for limitation in summary["limitations"])
