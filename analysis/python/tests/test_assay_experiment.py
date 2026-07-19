"""Scientific and design tests for the first Development Experiment slice."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from pyarrow import parquet
from transcriptforge_analysis.assay_experiment import (
    run_input_degradation_experiment,
    validate_input_degradation_design,
)
from transcriptforge_analysis.expression_bundle import BundleConfig, build_expression_bundle
from transcriptforge_analysis.matrix_validation import ValidationConfig


def _spec() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "experiment": {
            "experiment_id": "exp-ffpe-input",
            "name": "Synthetic FFPE input exploration",
            "type": "INPUT_DEGRADATION_EXPLORATION",
            "stage": "FEASIBILITY",
            "objective": "Explore paired profile stability across RNA input levels.",
            "exploratory": True,
            "mode": "ANALYZE_EXISTING",
            "revision": 1,
        },
        "assay_context": {
            "specimen_type": "simulated_ffpe_tumor",
            "proposed_output": "expression_classifier_score",
            "assay_version": "development-unlocked",
        },
        "question": {
            "question_key": "input_degradation_stability",
            "plain_language": "Does RNA input or degradation affect expression stability?",
            "decision_to_inform": "Whether 25 ng remains a candidate development condition.",
        },
        "inputs": {
            "assignment_table": "design/experiment_assignments.tsv",
            "expression_bundles": [{"prepared_dataset_id": "prepared-ffpe", "role": "development"}],
        },
        "sample_structure": {
            "measurement_id": "measurement_id",
            "biological_sample_id": "biological_sample_id",
            "replicate_id": "replicate_id",
            "pair_id": "biological_sample_id",
        },
        "factors": [
            {"name": "input_ng", "type": "ordered_numeric", "role": "primary"},
            {"name": "dv200", "type": "continuous", "role": "covariate"},
            {"name": "sequencing_run", "type": "categorical", "role": "blocking"},
        ],
        "endpoints": {
            "primary": ["expression_profile_correlation_to_reference", "detected_genes"],
            "secondary": ["mean_expression"],
        },
        "analysis_plan": {
            "template": "ordered_level_paired_exploration",
            "assay": "log_expression",
            "reference_level": 100,
            "confidence_level": 0.95,
            "missing_value_policy": "fail_required_endpoint",
        },
        "success_guidance": {
            "mode": "exploratory",
            "declared_questions": ["Is profile correlation stable through 25 ng?"],
        },
        "rationales": {
            "reference_level": "Highest routinely available input condition.",
            "endpoint_choice": "Profile stability precedes classifier development.",
        },
    }


def _assignment_rows() -> list[dict[str, str]]:
    rows = []
    for sample_index, sample in enumerate(("bio-1", "bio-2"), start=1):
        for input_ng, suffix, dv200 in ((100, "100", 72), (50, "50", 61), (25, "25", 49)):
            rows.append(
                {
                    "measurement_id": f"s{sample_index}_{suffix}",
                    "biological_sample_id": sample,
                    "prepared_dataset_id": "prepared-ffpe",
                    "include": "true",
                    "exclusion_reason": "",
                    "replicate_id": suffix,
                    "input_ng": str(input_ng),
                    "dv200": str(dv200),
                    "sequencing_run": f"run-{sample_index}",
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
    matrix = tmp_path / "matrix.tsv"
    metadata = tmp_path / "metadata.tsv"
    samples = [row["measurement_id"] for row in _assignment_rows()]
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
                            80
                            + feature * 13
                            + (sample_index // 3) * 9
                            + (sample_index % 3) * ((-1) ** feature) * feature
                        )
                        for sample_index in range(6)
                    ],
                ]
            )
            for feature in range(1, 13)
        )
        + "\n",
        encoding="utf-8",
    )
    metadata.write_text(
        "sample_id\tcondition\n" + "".join(f"{sample}\tinput_exploration\n" for sample in samples),
        encoding="utf-8",
    )
    output = tmp_path / "bundle-output"
    build_expression_bundle(
        BundleConfig(
            validation=ValidationConfig(
                dataset_id="dataset-ffpe",
                name="Synthetic FFPE input",
                matrix_path=matrix,
                metadata_path=metadata,
                matrix_orientation="features_by_samples",
                feature_id_column="feature_id",
                sample_id_column="sample_id",
                value_type="raw_counts",
            ),
            prepared_dataset_id="prepared-ffpe",
            prepared_version=1,
        ),
        output,
    )
    return output / "expression_bundle.tar.gz"


def test_design_blocks_perfect_input_run_confounding() -> None:
    rows = _assignment_rows()
    for row in rows:
        row["sequencing_run"] = f"run-{row['input_ng']}"
    result = validate_input_degradation_design(_spec(), rows)
    assert result.valid is False
    assert "DESIGN.INPUT_RUN_CONFOUNDED" in {
        item.code for item in result.findings if item.severity == "ERROR"
    }


def test_design_distinguishes_estimable_imbalance_from_blocking_error() -> None:
    rows = _assignment_rows()
    rows[-1]["sequencing_run"] = "run-1"
    result = validate_input_degradation_design(_spec(), rows)
    assert result.valid is True
    assert "DESIGN.INPUT_RUN_IMBALANCE" in {
        item.code for item in result.findings if item.severity == "WARNING"
    }


def test_input_degradation_evidence_bundle_is_deterministic_and_explicit(
    tmp_path: Path,
) -> None:
    archive = _bundle(tmp_path)
    spec_path = tmp_path / "experiment-spec.json"
    assignment_path = tmp_path / "assignments.tsv"
    spec_path.write_text(json.dumps(_spec(), indent=2), encoding="utf-8")
    _write_assignments(assignment_path, _assignment_rows())

    first = tmp_path / "first"
    second = tmp_path / "second"
    first_manifest = run_input_degradation_experiment(spec_path, assignment_path, archive, first)
    second_manifest = run_input_degradation_experiment(spec_path, assignment_path, archive, second)

    assert first_manifest == second_manifest
    first_bundle = first / "development_evidence_bundle"
    second_bundle = second / "development_evidence_bundle"
    for relative in (
        "manifest.json",
        "experiment_spec.yaml",
        "question.json",
        "design/design_validation.json",
        "endpoints/endpoint_table.parquet",
        "endpoints/endpoint_table.tsv.gz",
        "results/primary_results.json",
        "decision/decision_summary.json",
        "decision/recommendations.json",
        "figures/profile_stability_by_input.svg",
        "report/development_report.html",
        "report/development_report.pdf",
    ):
        assert (first_bundle / relative).read_bytes() == (second_bundle / relative).read_bytes()

    summary = json.loads(
        (first_bundle / "decision/decision_summary.json").read_text(encoding="utf-8")
    )
    assert summary["criteria_mode"] == "exploratory"
    assert summary["scientist_decision_required"] is True
    assert any("does not establish" in item for item in summary["limitations"])
    root = Path(__file__).parents[3]
    manifest_schema = json.loads(
        (root / "contracts/experiment/development_evidence_manifest.schema.json").read_text()
    )
    summary_schema = json.loads(
        (root / "contracts/experiment/decision_summary.schema.json").read_text()
    )
    Draft202012Validator(manifest_schema).validate(first_manifest)
    Draft202012Validator(summary_schema).validate(summary)
    endpoint_table = parquet.read_table(first_bundle / "endpoints/endpoint_table.parquet")
    assert endpoint_table.num_rows == len(_assignment_rows())
    assert (first_bundle / "report/development_report.pdf").read_bytes().startswith(b"%PDF-1.4")
    recommendations = json.loads(
        (first_bundle / "decision/recommendations.json").read_text(encoding="utf-8")
    )
    assert (
        recommendations["recommendations"][0]["one_click_action_template"]["launch_automatically"]
        is False
    )
    assert (first / "development_evidence_bundle.tar.gz").is_file()
