"""Versioned contract tests for guided assay development."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[3]
CONTRACTS = ROOT / "contracts"
EXAMPLES = CONTRACTS / "examples"
CATALOG = ROOT / "apps/api/transcriptforge_api/resources/scientific_question_catalog.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


CONTRACT_EXAMPLES = [
    ("assay_project/assay_project.schema.json", "assay_project.example.json"),
    ("assay_project/scientific_question.schema.json", "scientific_question.example.json"),
    ("guidance/readiness.schema.json", "readiness.example.json"),
    ("guidance/recommendation.schema.json", "recommendation.example.json"),
    ("guidance/decision_record.schema.json", "decision_record.example.json"),
    ("guidance/guidance_result.schema.json", "guidance_result.example.json"),
    ("experiment/experiment_spec.schema.json", "experiment_spec.example.json"),
    (
        "experiment/development_evidence_manifest.schema.json",
        "development_evidence_manifest.example.json",
    ),
    ("experiment/decision_summary.schema.json", "experiment_decision_summary.example.json"),
    ("model/model_manifest.schema.json", "model_manifest.example.json"),
    ("validation/study_spec.schema.json", "study_spec.example.json"),
    (
        "validation/validation_bundle_manifest.schema.json",
        "validation_bundle_manifest.example.json",
    ),
]


@pytest.mark.parametrize(("schema_path", "example_name"), CONTRACT_EXAMPLES)
def test_assay_development_contract_and_example(schema_path: str, example_name: str) -> None:
    schema = load_json(CONTRACTS / schema_path)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(
        load_json(EXAMPLES / example_name)
    )


def test_question_catalog_is_valid_and_routes_each_question_once() -> None:
    schema = load_json(CONTRACTS / "guidance/question_catalog.schema.json")
    catalog = load_json(CATALOG)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(catalog)

    keys = [question["key"] for question in catalog["questions"]]
    assert len(keys) == len(set(keys))
    assert {question["stage"] for question in catalog["questions"]} >= {
        "FEASIBILITY",
        "EXPLORE",
        "OPTIMIZE",
        "DEVELOP",
        "LOCK",
        "VALIDATE",
    }


def test_only_implemented_guided_surfaces_are_enabled_by_default() -> None:
    from transcriptforge_api.config import Settings

    settings = Settings(_env_file=None)
    assert settings.guided_assay_development_enabled is True
    assert settings.assay_experiment_execution_enabled is True
    assert settings.assay_study_execution_enabled is True


def test_catalog_experiment_and_study_routes_have_lifecycle_handlers() -> None:
    from transcriptforge_api.services.experiments import IMPLEMENTED_EXPERIMENT_ROUTES
    from transcriptforge_api.services.studies import IMPLEMENTED_STUDY_ROUTES

    catalog = load_json(CATALOG)
    experiment_routes = {
        question["experiment_type"]: question["key"]
        for question in catalog["questions"]
        if "experiment_type" in question
    }
    study_routes = {
        question["study_type"]: question["key"]
        for question in catalog["questions"]
        if "study_type" in question
    }
    assert experiment_routes == IMPLEMENTED_EXPERIMENT_ROUTES
    assert study_routes == IMPLEMENTED_STUDY_ROUTES
