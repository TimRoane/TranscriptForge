"""Cross-language JSON Schema contract tests."""

import hashlib
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
        "deconvolution_method_registry.schema.json",
        "deconvolution_reference.schema.json",
        "deconvolution_results.schema.json",
        "enrichment_summary.schema.json",
        "expression_bundle.schema.json",
        "microarray_ingestion.schema.json",
        "microarray_platform.schema.json",
        "public_signature_benchmark.schema.json",
        "analysis_request.schema.json",
        "cross_modality_signature_acceptance.schema.json",
        "raw_rnaseq_ingestion.schema.json",
        "reference_bundle.schema.json",
        "result_manifest.schema.json",
        "sample_metadata.schema.json",
        "signature_definition.schema.json",
        "signature_mapping.schema.json",
        "signature_scores.schema.json",
        "validation_report.schema.json",
    ],
)
def test_schema_is_valid_draft_2020_12(schema_name: str) -> None:
    Draft202012Validator.check_schema(load_json(SCHEMAS / schema_name))


def test_demo_count_manifest_is_valid() -> None:
    schema = load_json(SCHEMAS / "dataset_manifest.schema.json")
    manifest = load_json(ROOT / "demo/configs/count_matrix_dataset_manifest.json")
    Draft202012Validator(schema).validate(manifest)


def test_deconvolution_registry_is_valid_and_semantically_distinct() -> None:
    schema = load_json(SCHEMAS / "deconvolution_method_registry.schema.json")
    registry = load_json(ROOT / "apps/api/transcriptforge_api/resources/deconvolution_methods.json")
    Draft202012Validator(schema).validate(registry)
    methods = {item["id"]: item for item in registry["methods"]}
    assert methods["epic"]["result_type"] == "cell_fraction"
    assert methods["quantiseq"]["unit"] == "fraction"
    assert methods["mcp_counter"]["result_type"] == "enrichment_score"
    assert methods["xcell"]["composition_constraint"] == "not_compositional"


def test_quantiseq_reference_manifest_is_valid() -> None:
    schema = load_json(SCHEMAS / "deconvolution_reference.schema.json")
    reference = load_json(ROOT / "references/deconvolution/quantiseq_til10.json")
    Draft202012Validator(schema).validate(reference)
    assert reference["package"]["version"] == "1.18.0"
    assert reference["signature_gene_count"] == 170


def test_deconvolution_analysis_request_and_result_type_contracts() -> None:
    request_schema = load_json(SCHEMAS / "analysis_request.schema.json")
    method = load_json(ROOT / "apps/api/transcriptforge_api/resources/deconvolution_methods.json")[
        "methods"
    ][0]
    request = {
        "schema_version": "1.0.0",
        "analysis_id": "deconvolution-1",
        "prepared_dataset_id": "prepared-1",
        "analysis_type": "deconvolution",
        "method": "epic",
        "assay": "tpm",
        "parameters": {
            "reference_profile": "TRef",
            "minimum_gene_overlap": 0.5,
            "tumor_mode": False,
            "scale_mrna": True,
        },
        "random_seed": 0,
        "method_registry_version": "2026.07.0",
        "method_registry_sha256": "a" * 64,
        "deconvolution_method": method,
        "input_assay_descriptor": {
            "name": "tpm",
            "path": "assays/tpm.tsv.gz",
            "scale": "linear",
            "value_type": "nonnegative_continuous",
            "feature_level": "gene",
            "sha256": "b" * 64,
        },
    }
    Draft202012Validator(request_schema).validate(request)
    request["assay"] = "log_expression"
    with pytest.raises(ValidationError):
        Draft202012Validator(request_schema).validate(request)

    result_schema = load_json(SCHEMAS / "deconvolution_results.schema.json")
    result = {
        "schema_version": "1.0.0",
        "analysis_id": "deconvolution-1",
        "prepared_dataset_id": "prepared-1",
        "method": "epic",
        "method_registry_version": "2026.07.0",
        "method_registry_sha256": "a" * 64,
        "result_type": "cell_fraction",
        "quantity_label": "Estimated cell fraction",
        "unit": "fraction",
        "composition_constraint": "bounded_sum",
        "input_validation": {
            "assay": "tpm",
            "scale": "linear",
            "value_type": "nonnegative_continuous",
            "feature_level": "gene",
            "identifier_namespace": "gene_symbol",
            "input_feature_count": 1000,
            "reference_gene_count": 100,
            "overlap_gene_count": 90,
            "overlap_fraction": 0.9,
            "minimum_overlap_fraction": 0.5,
            "passed": True,
        },
        "reference": {
            "id": "TRef",
            "version": "pinned-test",
            "sha256": "c" * 64,
            "cell_type_count": 2,
        },
        "cell_types": [{"id": "b_cell", "label": "B cells"}],
        "sample_ids": ["sample_1"],
        "estimates": [{"sample_id": "sample_1", "cell_type_id": "b_cell", "value": 0.2}],
        "composition_summaries": [
            {
                "sample_id": "sample_1",
                "reported_sum": 0.2,
                "residual_fraction": 0.8,
                "within_tolerance": True,
            }
        ],
        "warnings": [],
        "software": {"language": "R"},
        "provenance": {
            "expression_bundle_sha256": "d" * 64,
            "analysis_request_sha256": "e" * 64,
            "reference_sha256": "c" * 64,
        },
    }
    Draft202012Validator(result_schema).validate(result)
    result["result_type"] = "enrichment_score"
    with pytest.raises(ValidationError):
        Draft202012Validator(result_schema).validate(result)


def test_pinned_human_reference_bundle_is_valid() -> None:
    schema = load_json(SCHEMAS / "reference_bundle.schema.json")
    reference = load_json(ROOT / "references/human/gencode_v50_grch38_salmon_1_11_4.json")
    Draft202012Validator(schema).validate(reference)


def test_affymetrix_platform_adapter_is_valid() -> None:
    schema = load_json(SCHEMAS / "microarray_platform.schema.json")
    adapter = load_json(ROOT / "microarray/platforms/affymetrix_hugene_1_0_st_v1.json")
    Draft202012Validator(schema).validate(adapter)


def test_tiny_raw_rnaseq_fixtures_match_reference_and_ingestion_contracts() -> None:
    reference_schema = load_json(SCHEMAS / "reference_bundle.schema.json")
    ingestion_schema = load_json(SCHEMAS / "raw_rnaseq_ingestion.schema.json")
    reference = load_json(ROOT / "demo/raw_rnaseq/reference/reference.json")
    Draft202012Validator(reference_schema).validate(reference)
    for layout in ("paired", "single"):
        ingestion = load_json(ROOT / f"demo/raw_rnaseq/{layout}/ingestion_manifest.json")
        Draft202012Validator(ingestion_schema).validate(ingestion)


def test_public_microarray_acceptance_manifest_is_valid() -> None:
    schema = load_json(SCHEMAS / "microarray_ingestion.schema.json")
    manifest = load_json(ROOT / "demo/microarray/rma_acceptance_manifest.json")
    Draft202012Validator(schema).validate(manifest)
    metadata = ROOT / "demo/microarray/sample_metadata.tsv"
    assert metadata.stat().st_size == manifest["sample_metadata"]["size_bytes"]
    assert (
        hashlib.sha256(metadata.read_bytes()).hexdigest() == (manifest["sample_metadata"]["sha256"])
    )


def test_public_microarray_limma_request_is_valid() -> None:
    schema = load_json(SCHEMAS / "analysis_request.schema.json")
    request = load_json(ROOT / "demo/microarray/limma_request.json")
    Draft202012Validator(schema).validate(request)


def test_public_signature_benchmark_is_frozen_and_passes() -> None:
    fixture = ROOT / "demo/signature_public_benchmark"
    schema = load_json(SCHEMAS / "public_signature_benchmark.schema.json")
    policy_path = fixture / "benchmark_policy.json"
    signature_path = fixture / "cartilage_zone_markers.gmt"
    result = load_json(fixture / "public_signature_benchmark.json")

    Draft202012Validator(schema).validate(result)
    assert result["policy_sha256"] == hashlib.sha256(policy_path.read_bytes()).hexdigest()
    assert result["signature"]["sha256"] == hashlib.sha256(signature_path.read_bytes()).hexdigest()
    assert result["recommendation"] == {
        "default_rerun_byte_identical": True,
        "eligible": True,
        "method": "mean_z_score",
        "raw_cross_cohort_threshold_permitted": False,
        "selection_rule": load_json(policy_path)["default_method_policy"]["rationale"],
    }
    assert result["passed"] is True
    assert all(method["passed"] for method in result["methods"])
    assert {method["method"] for method in result["methods"]} == {
        "mean_expression",
        "mean_z_score",
        "weighted_linear",
        "rank_based",
        "gsva",
        "ssgsea",
    }


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
            "enrichment": {
                "enabled": True,
                "collection_id": "transcriptforge_demo_effects",
                "ranking_metric": "signed_log10_p_value",
                "permutation_count": 250,
                "minimum_gene_set_size": 10,
                "maximum_gene_set_size": 500,
            },
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


def test_gsva_analysis_request_contract_freezes_method_parameters() -> None:
    schema = load_json(SCHEMAS / "analysis_request.schema.json")
    request = {
        "schema_version": "1.0.0",
        "analysis_id": "analysis-gsva-1",
        "prepared_dataset_id": "prepared-1",
        "analysis_type": "signature",
        "method": "gsva",
        "assay": "log_expression",
        "parameters": {
            "signature_mapping_id": "mapping-1",
            "minimum_gene_set_size": 2,
            "maximum_gene_set_size": 500,
            "gsva_kcdf": "Gaussian",
            "gsva_tau": 1,
            "gsva_max_diff": True,
            "gsva_abs_ranking": False,
            "ssgsea_alpha": 0.25,
            "ssgsea_normalize": True,
        },
        "signature_mapping": {
            "id": "mapping-1",
            "report_sha256": "a" * 64,
            "report": {"expression_bundle_sha256": "b" * 64},
        },
        "random_seed": 0,
    }
    Draft202012Validator(schema).validate(request)

    del request["parameters"]["gsva_tau"]
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(request)


def test_enrichment_summary_contract() -> None:
    schema = load_json(SCHEMAS / "enrichment_summary.schema.json")
    result = {
        "gene_set_id": "TF_DEMO_TREATMENT_UP",
        "gene_set_name": "Synthetic treatment-up controls",
        "direction": "up",
        "set_size": 150,
        "overlap_size": 31,
        "enrichment_score": 0.82,
        "normalized_enrichment_score": 2.1,
        "odds_ratio": None,
        "p_value": 0.004,
        "adjusted_p_value": 0.028,
        "leading_edge": ["gene_00001"],
        "significant": True,
    }
    summary = {
        "schema_version": "1.0.0",
        "analysis_id": "analysis-de-1",
        "collection": {
            "collection_id": "transcriptforge_demo_effects",
            "name": "TranscriptForge synthetic experiment controls",
            "version": "1.0.0",
            "identifier_namespace": "transcriptforge_demo_feature_id",
            "source": "TranscriptForge bundled deterministic demo experiment",
            "license": "PolyForm-Noncommercial-1.0.0",
            "gmt_sha256": "b" * 64,
            "set_count": 7,
        },
        "source_result": {
            "method": "edgeR QL",
            "contrast": "treated versus control within treatment",
            "result_sha256": "a" * 64,
            "tested_feature_count": 2000,
            "significant_feature_count": 31,
        },
        "parameters": {
            "identifier_field": "feature_id",
            "ranking_metric": "signed_log10_p_value",
            "random_seed": 42,
            "permutation_count": 250,
            "minimum_gene_set_size": 10,
            "maximum_gene_set_size": 500,
            "fdr_threshold": 0.05,
            "absolute_log2_fold_change": 1,
        },
        "ranked_list": [result],
        "over_representation": [
            {
                **result,
                "enrichment_score": None,
                "normalized_enrichment_score": None,
                "odds_ratio": 4.2,
            }
        ],
        "warnings": ["Synthetic demonstration controls."],
    }
    Draft202012Validator(schema).validate(summary)
