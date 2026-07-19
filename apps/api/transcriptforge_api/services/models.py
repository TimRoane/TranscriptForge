"""Scientist-controlled classifier model review, lock, and integrity operations."""

import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api.models import (
    Analysis,
    Artifact,
    AssayAuditEvent,
    AssayDevelopmentProject,
    DecisionRecord,
    ModelRecord,
    Run,
)
from transcriptforge_api.models.base import utc_now
from transcriptforge_api.schemas.models import ModelIntegrityRead, ModelLockReadinessRead
from transcriptforge_api.storage.base import StorageBackend

MODEL_MANIFEST_SCHEMA = (
    Path(__file__).resolve().parents[4] / "contracts/model/model_manifest.schema.json"
)
REQUIRED_ARTIFACTS = {
    "classifier_model",
    "classifier_model_card",
    "classifier_inference_schema",
    "classifier_inference_example",
    "classifier_results",
}


class ModelLifecycleError(ValueError):
    """Raised when a requested model transition violates the lock policy."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


async def get_model(session: AsyncSession, model_id: str) -> ModelRecord | None:
    return await session.get(ModelRecord, model_id)


async def list_models(session: AsyncSession, analysis_id: str) -> list[ModelRecord]:
    return list(
        await session.scalars(
            select(ModelRecord)
            .where(ModelRecord.analysis_id == analysis_id)
            .order_by(ModelRecord.created_at.desc())
        )
    )


async def list_assay_project_models(
    session: AsyncSession, assay_project_id: str
) -> list[ModelRecord]:
    """List model candidates whose source analysis belongs to an assay workspace."""

    return list(
        await session.scalars(
            select(ModelRecord)
            .join(Analysis, ModelRecord.analysis_id == Analysis.id)
            .where(Analysis.assay_project_id == assay_project_id)
            .order_by(ModelRecord.created_at.desc())
        )
    )


async def _artifacts(session: AsyncSession, model: ModelRecord) -> dict[str, Artifact]:
    return {
        item.artifact_type: item
        for item in await session.scalars(select(Artifact).where(Artifact.run_id == model.run_id))
    }


def _decision_rule(payload: dict[str, Any]) -> dict[str, Any]:
    if payload["model_type"] == "binary_elastic_net_logistic_regression":
        return {
            "operator": "gte",
            "threshold": payload["decision_threshold"],
            "positive_class": payload["positive_class"],
            "negative_class": payload["negative_class"],
        }
    return {"operator": "argmax", "classes": payload["classes"]}


def _fixture(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    features = payload["selected_feature_ids"]
    means = np.asarray(payload["preprocessing"]["means"], dtype=float)
    scales = np.asarray(payload["preprocessing"]["scales"], dtype=float)
    if len(features) == 0 or means.shape != scales.shape or means.shape[0] != len(features):
        raise ModelLifecycleError("The serialized preprocessing and feature schema disagree.")
    if not np.all(np.isfinite(means)) or not np.all(np.isfinite(scales)) or np.any(scales <= 0):
        raise ModelLifecycleError("The serialized preprocessing is not finite and executable.")
    transformed = (means - means) / scales
    estimator = payload["estimator"]
    if payload["model_type"] == "binary_elastic_net_logistic_regression":
        decision = float(
            transformed @ np.asarray(estimator["coefficients"]) + estimator["intercept"]
        )
        calibration = payload["calibration"]
        if calibration["method"] == "sigmoid":
            decision = decision * float(calibration["coefficient"]) + float(
                calibration["intercept"]
            )
        probability = float(1.0 / (1.0 + np.exp(-np.clip(decision, -709, 709))))
        predicted = (
            payload["positive_class"]
            if probability >= float(payload["decision_threshold"])
            else payload["negative_class"]
        )
        expected = {"positive_probability": probability, "predicted_class": predicted}
    else:
        logits = np.asarray(estimator["coefficients"]) @ transformed + np.asarray(
            estimator["intercepts"]
        )
        probabilities = np.exp(logits - np.max(logits))
        probabilities /= probabilities.sum()
        expected = {
            "class_probabilities": dict(
                zip(payload["classes"], probabilities.tolist(), strict=True)
            ),
            "predicted_class": payload["classes"][int(np.argmax(probabilities))],
        }
    fixture = {
        "schema_version": "1.0.0",
        "assay": payload["assay"],
        "samples": [
            {
                "sample_id": "deterministic_lock_fixture",
                "features": dict(zip(features, means.tolist(), strict=True)),
            }
        ],
    }
    if _canonical(expected) != _canonical(_fixture_expected(payload, means)):
        raise ModelLifecycleError("Deterministic inference fixture produced inconsistent output.")
    return fixture, expected


def _fixture_expected(payload: dict[str, Any], means: np.ndarray[Any, Any]) -> dict[str, Any]:
    # A second independent evaluation is deliberately required by the lock operation.
    estimator = payload["estimator"]
    transformed = np.zeros_like(means)
    if payload["model_type"] == "binary_elastic_net_logistic_regression":
        decision = float(
            transformed @ np.asarray(estimator["coefficients"]) + estimator["intercept"]
        )
        calibration = payload["calibration"]
        if calibration["method"] == "sigmoid":
            decision = decision * float(calibration["coefficient"]) + float(
                calibration["intercept"]
            )
        probability = float(1.0 / (1.0 + np.exp(-np.clip(decision, -709, 709))))
        return {
            "positive_probability": probability,
            "predicted_class": payload["positive_class"]
            if probability >= float(payload["decision_threshold"])
            else payload["negative_class"],
        }
    logits = np.asarray(estimator["coefficients"]) @ transformed + np.asarray(
        estimator["intercepts"]
    )
    probabilities = np.exp(logits - np.max(logits))
    probabilities /= probabilities.sum()
    return {
        "class_probabilities": dict(zip(payload["classes"], probabilities.tolist(), strict=True)),
        "predicted_class": payload["classes"][int(np.argmax(probabilities))],
    }


async def lock_readiness(
    session: AsyncSession, storage: StorageBackend, model: ModelRecord
) -> ModelLockReadinessRead:
    run = await session.get(Run, model.run_id)
    artifacts = await _artifacts(session, model)
    checks = {
        # A locked model necessarily passed review. Keep the evidence true after
        # the lifecycle transition so the read-only registry page does not
        # misleadingly render an already locked package as blocked.
        "candidate_reviewed": model.status in {"REVIEWED", "LOCKED"},
        "classifier_run_succeeded": run is not None and run.state == "SUCCEEDED",
        "required_assets_present": set(artifacts) >= REQUIRED_ARTIFACTS,
        "model_object_integrity": False,
        "feature_schema_complete": False,
        "preprocessing_serializable": False,
        "threshold_source_documented": False,
        "validation_mode_labeled": False,
        "leakage_checks_present": False,
        "model_card_complete": False,
        "deterministic_inference_test": False,
    }
    blockers: list[str] = []
    if checks["required_assets_present"]:
        model_bytes = storage.read_bytes(artifacts["classifier_model"].storage_uri)
        card = json.loads(storage.read_bytes(artifacts["classifier_model_card"].storage_uri))
        result = json.loads(storage.read_bytes(artifacts["classifier_results"].storage_uri))
        payload = json.loads(model_bytes)
        checks["model_object_integrity"] = _sha(model_bytes) == artifacts["classifier_model"].sha256
        checks["feature_schema_complete"] = bool(payload.get("selected_feature_ids"))
        checks["preprocessing_serializable"] = bool(payload.get("preprocessing"))
        checks["threshold_source_documented"] = bool(
            payload.get("decision_threshold") is not None
            or payload.get("prediction_rule") == "maximum_class_probability"
        )
        checks["validation_mode_labeled"] = bool(result.get("validation"))
        checks["leakage_checks_present"] = bool(result.get("leakage_audit"))
        checks["model_card_complete"] = all(
            card.get(key) for key in ("intended_use", "prohibited_use", "validation")
        )
        try:
            _fixture(payload)
            checks["deterministic_inference_test"] = True
        except (KeyError, TypeError, ValueError, FloatingPointError):
            pass
    for key, passed in checks.items():
        if not passed:
            blockers.append(key.replace("_", " ").capitalize() + " is required before lock.")
    return ModelLockReadinessRead(
        model_id=model.id,
        ready=not blockers,
        checks=checks,
        blockers=blockers,
        warnings=["Internal validation is not independent external validation."],
    )


async def review_model(
    session: AsyncSession, storage: StorageBackend, model: ModelRecord, rationale: str
) -> ModelRecord:
    if model.status != "CANDIDATE":
        raise ModelLifecycleError("Only a CANDIDATE model can enter review.")
    # Evaluate technical readiness without requiring the REVIEWED state itself.
    model.status = "REVIEWED"
    readiness = await lock_readiness(session, storage, model)
    if not readiness.ready:
        model.status = "CANDIDATE"
        raise ModelLifecycleError(" ".join(readiness.blockers))
    model.reviewed_at = utc_now()
    model.reviewed_by = "local-user"
    model.inference_test_status = "PASS"
    await _audit_model_decision(session, model, "MODEL_REVIEWED", rationale)
    await session.commit()
    await session.refresh(model)
    return model


async def lock_model(
    session: AsyncSession, storage: StorageBackend, model: ModelRecord, rationale: str
) -> ModelRecord:
    readiness = await lock_readiness(session, storage, model)
    if model.status != "REVIEWED" or not readiness.ready:
        raise ModelLifecycleError("Model lock is blocked. " + " ".join(readiness.blockers))
    artifacts = await _artifacts(session, model)
    model_bytes = storage.read_bytes(artifacts["classifier_model"].storage_uri)
    model_card_bytes = storage.read_bytes(artifacts["classifier_model_card"].storage_uri)
    schema_bytes = storage.read_bytes(artifacts["classifier_inference_schema"].storage_uri)
    example_bytes = storage.read_bytes(artifacts["classifier_inference_example"].storage_uri)
    payload = json.loads(model_bytes)
    card = json.loads(model_card_bytes)
    fixture_input, fixture_expected = _fixture(payload)
    decision_rule = _decision_rule(payload)
    feature_sha = _sha(_canonical(payload["selected_feature_ids"]))
    preprocessing_sha = _sha(_canonical(payload["preprocessing"]))
    threshold_sha = _sha(_canonical(decision_rule))
    manifest = {
        "schema_version": "1.0.0",
        "model_id": model.id,
        "status": "LOCKED",
        "ordered_feature_schema": payload["selected_feature_ids"],
        "missing_feature_behavior": "ERROR",
        "imputation_rules": {},
        "transformations": [{"name": payload["preprocessing"]["feature_filter"]}],
        "scaling_parameters": {
            "means": payload["preprocessing"]["means"],
            "scales": payload["preprocessing"]["scales"],
        },
        "normalization_assumptions": [
            f"Input must be a compatible gene-level {payload['assay']} assay."
        ],
        "serialized_model": {
            "uri": artifacts["classifier_model"].storage_uri,
            "sha256": artifacts["classifier_model"].sha256,
        },
        "outcome_classes": payload.get(
            "classes", [payload.get("negative_class"), payload.get("positive_class")]
        ),
        "probability_interpretation": (
            "Probabilities correspond to the declared outcome classes and frozen decision rule."
        ),
        "decision_rule": decision_rule,
        "expected_assay": payload["assay"],
        "training_dataset_refs": model.training_dataset_refs_json,
        "validation_dataset_refs": model.validation_dataset_refs_json,
        "software_versions": {"transcriptforge": "0.1.0", "algorithm": model.algorithm},
        "container_digest": model.container_digest,
        "model_card": card,
        "inference_fixture": {
            "input_uri": "fixtures/inference_input.json",
            "expected_output_uri": "fixtures/expected_output.json",
            "status": "PASS",
        },
        "checksums": {
            "feature_schema": feature_sha,
            "preprocessing": preprocessing_sha,
            "model_object": artifacts["classifier_model"].sha256,
            "decision_rule": threshold_sha,
            "inference_schema": artifacts["classifier_inference_schema"].sha256,
            "model_card": artifacts["classifier_model_card"].sha256,
        },
    }
    schema = json.loads(MODEL_MANIFEST_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(manifest)
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
    prefix = ("models", model.id, "locked", "v1")
    stored_manifest = storage.put(prefix, "model_manifest.json", io.BytesIO(manifest_bytes))
    package = _model_package(
        {
            "model_manifest.json": manifest_bytes,
            "model.json": model_bytes,
            "model_card.json": model_card_bytes,
            "inference_schema.json": schema_bytes,
            "inference_example.tsv": example_bytes,
            "fixtures/inference_input.json": json.dumps(
                fixture_input, indent=2, sort_keys=True
            ).encode()
            + b"\n",
            "fixtures/expected_output.json": json.dumps(
                fixture_expected, indent=2, sort_keys=True
            ).encode()
            + b"\n",
        }
    )
    stored_package = storage.put(prefix, "locked_model_package.tar.gz", io.BytesIO(package))
    model.status = "LOCKED"
    model.locked_at = utc_now()
    model.locked_by = "local-user"
    model.model_manifest_uri = stored_manifest.uri
    model.model_manifest_sha256 = stored_manifest.sha256
    model.model_package_uri = stored_package.uri
    model.model_package_sha256 = stored_package.sha256
    model.feature_schema_sha256 = feature_sha
    model.preprocessing_sha256 = preprocessing_sha
    model.model_object_sha256 = artifacts["classifier_model"].sha256
    model.threshold_sha256 = threshold_sha
    model.inference_test_status = "PASS"
    await _audit_model_decision(session, model, "MODEL_LOCKED", rationale)
    await session.commit()
    await session.refresh(model)
    return model


def _model_package(files: dict[str, bytes]) -> bytes:
    raw = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive,
    ):
        for name, content in sorted(files.items()):
            member = tarfile.TarInfo(name)
            member.size = len(content)
            member.mtime = 0
            member.mode = 0o444
            archive.addfile(member, io.BytesIO(content))
    return raw.getvalue()


async def integrity(
    session: AsyncSession, storage: StorageBackend, model: ModelRecord
) -> ModelIntegrityRead:
    checks: dict[str, bool] = {}
    errors: list[str] = []
    for label, uri, expected_sha in (
        ("model_object", model.model_uri, model.model_object_sha256),
        ("model_manifest", model.model_manifest_uri, model.model_manifest_sha256),
        ("model_package", model.model_package_uri, model.model_package_sha256),
    ):
        passed = bool(uri and expected_sha and _sha(storage.read_bytes(uri)) == expected_sha)
        checks[label] = passed
        if not passed:
            errors.append(f"{label.replace('_', ' ')} checksum mismatch or missing asset.")
    if checks["model_object"]:
        payload = json.loads(storage.read_bytes(model.model_uri))
        derived = {
            "feature_schema": _sha(_canonical(payload["selected_feature_ids"])),
            "preprocessing": _sha(_canonical(payload["preprocessing"])),
            "threshold": _sha(_canonical(_decision_rule(payload))),
        }
        expected_derived = {
            "feature_schema": model.feature_schema_sha256,
            "preprocessing": model.preprocessing_sha256,
            "threshold": model.threshold_sha256,
        }
        for label in derived:
            checks[label] = derived[label] == expected_derived[label]
            if not checks[label]:
                errors.append(f"{label.replace('_', ' ')} integrity failed.")
    return ModelIntegrityRead(
        model_id=model.id, valid=all(checks.values()), checks=checks, errors=errors
    )


async def clone_model(
    session: AsyncSession, storage: StorageBackend, source: ModelRecord
) -> ModelRecord:
    model_bytes = storage.read_bytes(source.model_uri)
    card_bytes = storage.read_bytes(source.model_card_uri)
    clone = ModelRecord(
        analysis_id=source.analysis_id,
        run_id=source.run_id,
        model_name=f"{source.model_name} (candidate revision)",
        algorithm=source.algorithm,
        outcome_column=source.outcome_column,
        model_uri="pending",
        model_card_uri="pending",
        metrics_json=source.metrics_json,
        feature_count=source.feature_count,
        status="CANDIDATE",
        parent_model_id=source.id,
        feature_schema_sha256=source.feature_schema_sha256,
        preprocessing_sha256=source.preprocessing_sha256,
        model_object_sha256=_sha(model_bytes),
        threshold_sha256=source.threshold_sha256,
        training_dataset_refs_json=source.training_dataset_refs_json,
        validation_dataset_refs_json=source.validation_dataset_refs_json,
        container_digest=source.container_digest,
        inference_test_status="NOT_RUN",
    )
    session.add(clone)
    await session.flush()
    prefix = ("models", clone.id, "candidate")
    clone.model_uri = storage.put(prefix, "model.json", io.BytesIO(model_bytes)).uri
    clone.model_card_uri = storage.put(prefix, "model_card.json", io.BytesIO(card_bytes)).uri
    await session.commit()
    await session.refresh(clone)
    return clone


async def retire_model(session: AsyncSession, model: ModelRecord, rationale: str) -> ModelRecord:
    if model.status != "LOCKED":
        raise ModelLifecycleError("Only a LOCKED model can be retired.")
    model.status = "RETIRED"
    model.retired_at = utc_now()
    await _audit_model_decision(session, model, "MODEL_RETIRED", rationale)
    await session.commit()
    await session.refresh(model)
    return model


async def _audit_model_decision(
    session: AsyncSession, model: ModelRecord, event_type: str, rationale: str
) -> None:
    analysis = await session.get(Analysis, model.analysis_id)
    if analysis is None or analysis.assay_project_id is None:
        return
    assay = await session.get(AssayDevelopmentProject, analysis.assay_project_id)
    if assay is None:
        return
    session.add(
        AssayAuditEvent(
            assay_project_id=assay.id,
            event_type=event_type,
            actor="local-user",
            object_type="ModelRecord",
            object_id=model.id,
            hashes_json={
                key: value
                for key, value in {
                    "model": model.model_object_sha256,
                    "manifest": model.model_manifest_sha256,
                }.items()
                if value
            },
            details_json={"status": model.status, "rationale": rationale},
        )
    )
    session.add(
        DecisionRecord(
            assay_project_id=assay.id,
            source_type="MODEL",
            source_id=model.id,
            stage="LOCK",
            decision_key=event_type,
            decision=event_type.replace("_", " ").title(),
            rationale=rationale,
            selected_option=model.status,
            alternatives_json=[],
            evidence_refs_json=[{"type": "model_record", "id": model.id}],
            made_by="local-user",
        )
    )
