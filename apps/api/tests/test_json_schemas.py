"""Cross-language JSON Schema contract tests."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).parents[3]
SCHEMAS = ROOT / "schemas"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


@pytest.mark.parametrize(
    "schema_name",
    [
        "dataset_manifest.schema.json",
        "expression_bundle.schema.json",
        "analysis_request.schema.json",
        "result_manifest.schema.json",
        "sample_metadata.schema.json",
        "validation_report.schema.json",
    ],
)
def test_schema_is_valid_draft_2020_12(schema_name: str) -> None:
    Draft202012Validator.check_schema(load_json(SCHEMAS / schema_name))


def test_demo_count_manifest_is_valid() -> None:
    schema = load_json(SCHEMAS / "dataset_manifest.schema.json")
    manifest = load_json(ROOT / "demo/configs/count_matrix_dataset_manifest.json")
    Draft202012Validator(schema).validate(manifest)


def test_dataset_manifest_rejects_modality_source_mismatch() -> None:
    schema = load_json(SCHEMAS / "dataset_manifest.schema.json")
    manifest = load_json(ROOT / "demo/configs/count_matrix_dataset_manifest.json")
    manifest["modality"] = "microarray"

    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(manifest)


def test_differential_expression_analysis_request_contract() -> None:
    schema = load_json(SCHEMAS / "analysis_request.schema.json")
    request = {
        "schema_version": "1.0.0",
        "analysis_id": "analysis-de-1",
        "prepared_dataset_id": "prepared-1",
        "analysis_type": "differential_expression",
        "method": "deseq2",
        "assay": "raw_counts",
        "design_formula": "~ donor_id + batch + treatment",
        "contrast_label": "stimulated versus vehicle within treatment",
        "design_validation": {
            "sample_count": 8,
            "design_matrix_rank": 4,
            "design_matrix_columns": [
                "Intercept",
                "donor_id[2]",
                "batch[2]",
                "treatment[stimulated]",
            ],
            "warnings": [],
        },
        "parameters": {
            "design": {
                "primary_variable": "treatment",
                "covariates": ["batch"],
                "block_column": "donor_id",
                "interaction_terms": [],
                "reference_levels": {"treatment": "vehicle"},
            },
            "contrast": {
                "variable": "treatment",
                "numerator": "stimulated",
                "denominator": "vehicle",
            },
            "low_count_threshold": 10,
            "minimum_samples": 2,
            "fdr_threshold": 0.05,
            "absolute_log2_fold_change": 1,
            "independent_filtering": True,
            "shrinkage": True,
        },
        "random_seed": 42,
    }
    Draft202012Validator(schema).validate(request)

    request["method"] = "limma"
    request["assay"] = "log_expression"
    Draft202012Validator(schema).validate(request)

    request["method"] = "pca"
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(request)
