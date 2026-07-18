"""Validation and persistence helpers for one-shot external classifier studies."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import ValidationError  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api.models import ClassifierExternalValidation

MAX_ARTIFACT_BYTES = 10 * 1024 * 1024
SCHEMA_ROOT = Path(__file__).resolve().parents[4] / "schemas"

ARTIFACT_SPECS = {
    "protocol": (
        "Frozen prospective protocol",
        "classifier_external_validation_protocol.schema.json",
    ),
    "result": (
        "External validation result",
        "classifier_external_validation_results.schema.json",
    ),
    "prediction": (
        "Locked external predictions",
        "classifier_prediction_results.schema.json",
    ),
    "model": ("Locked classifier model", "classifier_model.schema.json"),
    "development_results": (
        "Development nested-CV results",
        "classifier_results.schema.json",
    ),
}


class ExternalValidationError(ValueError):
    """Raised when imported artifacts do not form one provenance-consistent study."""


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_and_validate(payload: bytes, artifact_name: str) -> dict[str, Any]:
    if not payload or len(payload) > MAX_ARTIFACT_BYTES:
        raise ExternalValidationError(
            f"{ARTIFACT_SPECS[artifact_name][0]} must contain 1 byte to 10 MiB."
        )
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExternalValidationError(
            f"{ARTIFACT_SPECS[artifact_name][0]} must be valid UTF-8 JSON."
        ) from error
    if not isinstance(document, dict):
        raise ExternalValidationError(
            f"{ARTIFACT_SPECS[artifact_name][0]} must contain a JSON object."
        )
    schema_name = ARTIFACT_SPECS[artifact_name][1]
    schema = json.loads((SCHEMA_ROOT / schema_name).read_text(encoding="utf-8"))
    try:
        Draft202012Validator(schema).validate(document)
    except ValidationError as error:
        location = ".".join(str(part) for part in error.absolute_path) or "document"
        raise ExternalValidationError(
            f"{ARTIFACT_SPECS[artifact_name][0]} failed schema validation at "
            f"{location}: {error.message}"
        ) from error
    return document


def validate_provenance(
    documents: dict[str, dict[str, Any]],
    payloads: dict[str, bytes],
    development_summary: dict[str, Any],
) -> dict[str, Any] | None:
    protocol = documents["protocol"]
    result = documents["result"]
    if protocol["protocol_id"] != result["protocol_id"]:
        raise ExternalValidationError("Protocol and result protocol IDs do not match.")
    if sha256(payloads["protocol"]) != result["provenance"]["protocol_sha256"]:
        raise ExternalValidationError(
            "The frozen protocol checksum does not match the external result provenance."
        )
    expected_samples = protocol["external_cohort"]["eligible_sample_count"]
    if result["sample_count"] != expected_samples:
        raise ExternalValidationError(
            "External result sample count does not match the frozen protocol."
        )
    protocol_counts = protocol["external_cohort"]["class_counts"]
    result_counts = result["class_counts"]
    if (
        result_counts["positive"] != protocol_counts[protocol["endpoint"]["positive_class"]]
        or result_counts["negative"] != protocol_counts[protocol["endpoint"]["negative_class"]]
    ):
        raise ExternalValidationError(
            "External result class counts do not match the frozen protocol."
        )

    development = documents.get("development_results")
    if development is not None:
        if development["analysis_id"] != result["model_analysis_id"]:
            raise ExternalValidationError(
                "Development result analysis ID does not match the evaluated model."
            )
        expected = {
            "sample_count": development["sample_count"],
            "input_feature_count": development["input_feature_count"],
            "roc_auc": development["metrics"]["roc_auc"],
            "roc_auc_lower": development["confidence_intervals"]["intervals"]["roc_auc"]["lower"],
            "roc_auc_upper": development["confidence_intervals"]["intervals"]["roc_auc"]["upper"],
            "pr_auc": development["metrics"]["pr_auc"],
        }
        for field, value in expected.items():
            supplied = development_summary[field]
            if isinstance(value, float):
                matches = math.isclose(supplied, value, rel_tol=1e-9, abs_tol=1e-12)
            else:
                matches = supplied == value
            if not matches:
                raise ExternalValidationError(
                    f"Development summary field '{field}' does not match classifier_results.json."
                )
        selected_count = development["top_variable_features"]
        if development_summary["selected_feature_count"] != selected_count:
            raise ExternalValidationError(
                "Development summary selected feature count does not match classifier results."
            )
        permutation = development.get("permutation_control")
        expected_p = permutation.get("empirical_p_value") if permutation else None
        supplied_p = development_summary.get("permutation_p_value")
        if (expected_p is None and supplied_p is not None) or (
            expected_p is not None
            and (supplied_p is None or not math.isclose(supplied_p, expected_p, rel_tol=1e-9))
        ):
            raise ExternalValidationError(
                "Development summary permutation p-value does not match classifier results."
            )

    model = documents.get("model")
    if model is not None:
        if model["analysis_id"] != result["model_analysis_id"]:
            raise ExternalValidationError("Locked model analysis ID does not match the result.")
        if sha256(payloads["model"]) != result["provenance"]["model_sha256"]:
            raise ExternalValidationError(
                "Locked model checksum does not match the external result provenance."
            )
        if development_summary["selected_feature_count"] != len(model["selected_feature_ids"]):
            raise ExternalValidationError(
                "Development summary selected feature count does not match the locked model."
            )

    prediction = documents.get("prediction")
    if prediction is None:
        return None
    if prediction["model_analysis_id"] != result["model_analysis_id"]:
        raise ExternalValidationError("Prediction model analysis ID does not match the result.")
    if prediction["sample_count"] != result["sample_count"]:
        raise ExternalValidationError("Prediction and external result sample counts do not match.")
    if sha256(payloads["prediction"]) != result["provenance"]["prediction_results_sha256"]:
        raise ExternalValidationError(
            "Prediction checksum does not match the external result provenance."
        )
    if prediction["provenance"]["model_sha256"] != result["provenance"]["model_sha256"]:
        raise ExternalValidationError("Prediction and result refer to different locked models.")
    positive = sum(row["predicted_positive"] for row in prediction["predictions"])
    return {
        "decision_threshold": prediction["decision_threshold"],
        "predicted_positive_count": positive,
        "predicted_negative_count": prediction["sample_count"] - positive,
        "positive_class": prediction["positive_class"],
        "negative_class": prediction["negative_class"],
    }


async def list_for_project(
    session: AsyncSession, project_id: str
) -> list[ClassifierExternalValidation]:
    records = await session.scalars(
        select(ClassifierExternalValidation)
        .where(ClassifierExternalValidation.project_id == project_id)
        .order_by(
            ClassifierExternalValidation.created_at.desc(),
            ClassifierExternalValidation.id.desc(),
        )
    )
    return list(records)


def to_read(record: ClassifierExternalValidation) -> dict[str, Any]:
    artifacts = [
        {"name": name, **{key: value for key, value in artifact.items() if key != "storage_uri"}}
        for name, artifact in record.artifacts_json.items()
    ]
    return {
        "id": record.id,
        "project_id": record.project_id,
        "name": record.name,
        "description": record.description,
        "development_accession": record.development_accession,
        "external_accession": record.external_accession,
        "protocol_id": record.protocol_id,
        "status": record.status,
        "development_summary": record.development_summary_json,
        "prediction_summary": record.prediction_summary_json,
        "protocol": record.protocol_json,
        "result": record.result_json,
        "artifacts": artifacts,
        "created_at": record.created_at,
    }
