"""Post-lock analytical-study persistence, validation, lock, and launch boundary."""

import csv
import gzip
import hashlib
import json
import tarfile
from io import BytesIO, StringIO, TextIOWrapper
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api.models import (
    AcceptanceCriterion,
    Analysis,
    AnalyticalStudy,
    Artifact,
    AssayDevelopmentProject,
    Dataset,
    ModelRecord,
    PreparedDataset,
    Run,
    ScientificQuestion,
    StudyInput,
)
from transcriptforge_api.models.base import new_id, utc_now
from transcriptforge_api.models.enums import RunState, RunType
from transcriptforge_api.schemas.studies import StudyCreate, StudyRead, StudyUpdate
from transcriptforge_api.services import models as model_service
from transcriptforge_api.services.design_validation import design_options
from transcriptforge_api.services.guided_assay import add_audit_event
from transcriptforge_api.services.study_design import (
    validate_input_degradation_limit_design,
    validate_paired_bridging_design,
    validate_precision_design,
    validate_robustness_interference_design,
)
from transcriptforge_api.storage.base import StorageBackend

EDITABLE_STATUSES = {"DRAFT", "DESIGN_VALID", "DESIGN_INVALID"}
ACTIVE_STATES = {"CREATED", "QUEUED", "STARTING", "RUNNING", "CANCELLING"}
STUDY_SCHEMA = Path(__file__).resolve().parents[4] / "contracts/validation/study_spec.schema.json"
IMPLEMENTED_STUDY_ROUTES = {
    "PRECISION_REPRODUCIBILITY": "precision_reproducibility",
    "INPUT_DEGRADATION_LIMIT": "input_degradation_limit_validation",
    "PAIRED_BRIDGING": "paired_bridging_equivalence",
    "ROBUSTNESS_INTERFERENCE": "robustness_interference_validation",
}


class StudyError(ValueError):
    """Raised when an analytical-study transition is invalid or unsafe."""


def _reference_level(request: StudyCreate) -> float:
    if request.reference_level is None:
        raise StudyError("Input/degradation limit studies require a reference level.")
    return request.reference_level


def _bridge_conditions(request: StudyCreate) -> tuple[str, str]:
    if request.reference_condition is None or request.comparator_condition is None:
        raise StudyError("A paired study requires reference and comparator/challenge conditions.")
    return request.reference_condition, request.comparator_condition


def study_read(study: AnalyticalStudy) -> StudyRead:
    return StudyRead.model_validate(study)


async def get_study(session: AsyncSession, study_id: str) -> AnalyticalStudy | None:
    return await session.get(AnalyticalStudy, study_id)


async def list_studies(session: AsyncSession, assay_project_id: str) -> list[AnalyticalStudy]:
    return list(
        await session.scalars(
            select(AnalyticalStudy)
            .where(AnalyticalStudy.assay_project_id == assay_project_id)
            .order_by(AnalyticalStudy.updated_at.desc())
        )
    )


async def _validate_links(
    session: AsyncSession,
    storage: StorageBackend,
    request: StudyCreate,
) -> tuple[AssayDevelopmentProject, ScientificQuestion, ModelRecord, PreparedDataset]:
    assay_project = await session.get(AssayDevelopmentProject, request.assay_project_id)
    question = await session.get(ScientificQuestion, request.question_id)
    model = await session.get(ModelRecord, request.model_id)
    prepared = await session.get(PreparedDataset, request.prepared_dataset_id)
    if assay_project is None:
        raise StudyError("Assay project not found.")
    if question is None or question.assay_project_id != assay_project.id:
        raise StudyError("The scientific question does not belong to this assay project.")
    expected_question = IMPLEMENTED_STUDY_ROUTES.get(request.study_type)
    if expected_question is None or question.question_key != expected_question:
        raise StudyError("The scientific question does not match this Analytical Study template.")
    if model is None or model.status != "LOCKED":
        raise StudyError("Select a LOCKED model before creating a validation study.")
    if prepared is None:
        raise StudyError("Prepared validation Expression Bundle not found.")
    dataset = await session.get(Dataset, prepared.dataset_id)
    analysis = await session.get(Analysis, model.analysis_id)
    if dataset is None or dataset.project_id != assay_project.project_id:
        raise StudyError("The validation Expression Bundle is outside this assay project.")
    if analysis is None or analysis.project_id != assay_project.project_id:
        raise StudyError("The locked model is outside this assay project.")
    integrity = await model_service.integrity(session, storage, model)
    if not integrity.valid:
        raise StudyError("Locked model integrity failed: " + " ".join(integrity.errors))
    if not model.model_manifest_uri or not model.model_manifest_sha256:
        raise StudyError("The locked model has no immutable ModelManifest.")
    manifest = json.loads(storage.read_bytes(model.model_manifest_uri))
    expected_assay = str(manifest["expected_assay"])
    if expected_assay not in prepared.value_types_available:
        raise StudyError(f"Validation bundle lacks the model's required '{expected_assay}' assay.")
    bundle_bytes = storage.read_bytes(prepared.bundle_uri)
    metadata_rows, _ = design_options(prepared, storage)
    expected_measurements = {row["sample_id"] for row in metadata_rows}
    assigned_measurements = {row.measurement_id for row in request.assignments}
    if assigned_measurements != expected_measurements:
        missing = sorted(expected_measurements - assigned_measurements)
        unexpected = sorted(assigned_measurements - expected_measurements)
        raise StudyError(
            "Study assignments must map every immutable bundle sample exactly once; "
            f"missing={missing[:5]}, unexpected={unexpected[:5]}."
        )
    model_payload = json.loads(storage.read_bytes(model.model_uri))
    available_features = _bundle_feature_ids(bundle_bytes, expected_assay)
    missing_features = sorted(set(model_payload["selected_feature_ids"]) - available_features)
    if missing_features:
        raise StudyError(
            "Validation bundle is incompatible with the locked feature schema; missing "
            + ", ".join(missing_features[:5])
            + "."
        )
    return assay_project, question, model, prepared


def _bundle_feature_ids(bundle: bytes, assay_name: str) -> set[str]:
    with tarfile.open(fileobj=BytesIO(bundle), mode="r:gz") as archive:
        manifest_source = archive.extractfile("expression_bundle/bundle_manifest.json")
        if manifest_source is None:
            raise StudyError("Expression Bundle manifest cannot be read.")
        manifest = json.load(manifest_source)
        assay = next(
            (item for item in manifest.get("assays", []) if item.get("name") == assay_name), None
        )
        if assay is None:
            raise StudyError(f"Expression Bundle does not declare assay '{assay_name}'.")
        relative = str(assay["path"])
        if relative.startswith("/") or ".." in relative.split("/"):
            raise StudyError("Expression Bundle assay path is unsafe.")
        archived_source = archive.extractfile(f"expression_bundle/{relative}")
        if archived_source is None:
            raise StudyError("Expression Bundle assay cannot be read.")
        source = (
            gzip.GzipFile(fileobj=archived_source) if relative.endswith(".gz") else archived_source
        )
        with source, TextIOWrapper(source, encoding="utf-8", newline="") as text:
            reader = csv.reader(text, delimiter="\t")
            header = next(reader, [])
            if not header or header[0] != "feature_id":
                raise StudyError("Expression Bundle assay is not canonical.")
            return {row[0] for row in reader if row}


def _build_spec(
    study_id: str,
    request: StudyCreate,
    assay_project: AssayDevelopmentProject,
    model: ModelRecord,
    design: dict[str, Any],
    *,
    revision: int = 1,
) -> dict[str, Any]:
    manifest_sha = model.model_manifest_sha256
    if manifest_sha is None:
        raise StudyError("The locked model manifest checksum is missing.")
    if request.study_type == "INPUT_DEGRADATION_LIMIT":
        factors = [
            {"name": "input_level", "type": "ordered_numeric", "treatment": "fixed"},
            {"name": "quality_metric", "type": "continuous", "treatment": "fixed"},
            {"name": "run", "type": "categorical", "treatment": "random"},
        ]
        endpoints = {
            "continuous": ["classifier_score", "score_difference_from_reference"],
            "categorical": ["predicted_class", "call_agreement_to_reference"],
            "qc": ["qc_failure"],
        }
        analysis_plan = {
            "template": "ordered_level_locked_endpoint_limit",
            "reference_level": request.reference_level,
            "confidence_level": request.confidence_level,
            "bootstrap_iterations": request.bootstrap_iterations,
            "threshold_proximity_band": request.threshold_proximity_band,
            "level_rationale": request.level_rationale,
        }
    elif request.study_type == "PAIRED_BRIDGING":
        factors = [
            {"name": "condition", "type": "categorical", "treatment": "fixed"},
            {"name": "run", "type": "categorical", "treatment": "random"},
            {"name": "subgroup", "type": "categorical", "treatment": "fixed"},
        ]
        endpoints = {
            "continuous": ["classifier_score", "paired_bias"],
            "categorical": ["predicted_class", "categorical_agreement"],
            "qc": [],
        }
        analysis_plan = {
            "template": "paired_locked_endpoint_bridging",
            "reference_condition": request.reference_condition,
            "comparator_condition": request.comparator_condition,
            "equivalence_margin": request.equivalence_margin,
            "condition_rationale": request.condition_rationale,
            "confidence_level": request.confidence_level,
            "bootstrap_iterations": request.bootstrap_iterations,
            "threshold_proximity_band": request.threshold_proximity_band,
            "correlation_passes_equivalence": False,
        }
    elif request.study_type == "ROBUSTNESS_INTERFERENCE":
        factors = [
            {"name": "condition", "type": "categorical", "treatment": "fixed"},
            {"name": "challenge_type", "type": "categorical", "treatment": "fixed"},
            {"name": "run", "type": "categorical", "treatment": "random"},
            {"name": "subgroup", "type": "categorical", "treatment": "fixed"},
        ]
        endpoints = {
            "continuous": ["classifier_score", "mean_challenge_effect"],
            "categorical": ["predicted_class", "call_change_rate"],
            "qc": ["qc_failure"],
        }
        analysis_plan = {
            "template": "paired_locked_endpoint_robustness_interference",
            "reference_condition": request.reference_condition,
            "challenge_condition": request.comparator_condition,
            "maximum_effect_margin": request.equivalence_margin,
            "condition_rationale": request.condition_rationale,
            "confidence_level": request.confidence_level,
            "bootstrap_iterations": request.bootstrap_iterations,
            "threshold_proximity_band": request.threshold_proximity_band,
            "biological_specificity_claims_supported": False,
        }
    else:
        factors = [
            {"name": factor, "type": "categorical", "treatment": "random"}
            for factor in request.factors
        ]
        endpoints = {
            "continuous": ["classifier_score"],
            "categorical": ["predicted_class"],
            "qc": [],
        }
        analysis_plan = {
            "template": "crossed_random_effects",
            "confidence_level": request.confidence_level,
            "bootstrap_iterations": request.bootstrap_iterations,
            "threshold_proximity_band": request.threshold_proximity_band,
        }
    return {
        "schema_version": "1.0.0",
        "study": {
            "study_id": study_id,
            "name": request.name,
            "type": request.study_type,
            "objective": request.objective,
            "revision": revision,
        },
        "assay_context": {
            "assay_name": assay_project.name,
            "assay_version": assay_project.assay_version or "locked-model-validation",
            "specimen_type": assay_project.specimen_type or "not-recorded",
            "intended_use_statement": assay_project.proposed_purpose
            or "Research demonstration only; not clinically validated.",
        },
        "model": {
            "model_id": model.id,
            "required_status": "LOCKED",
            "manifest_sha256": manifest_sha,
        },
        "inputs": {
            "assignment_table": "design/study_assignments.tsv",
            "expression_bundles": [
                {"prepared_dataset_id": request.prepared_dataset_id, "role": "validation"}
            ],
        },
        "sample_structure": {
            "measurement_id": "measurement_id",
            "biological_sample_id": "biological_sample_id",
            "replicate_id": "replicate_id",
        },
        "factors": factors,
        "endpoints": endpoints,
        "analysis_plan": analysis_plan,
        "acceptance_criteria": [item.model_dump(mode="json") for item in request.criteria],
        "design_validation": design,
    }


def _validate_contract(spec: dict[str, Any]) -> None:
    schema = json.loads(STUDY_SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(spec), key=lambda item: list(item.path)
    )
    if errors:
        location = ".".join(str(value) for value in errors[0].path) or "document"
        raise StudyError(f"StudySpec is invalid at {location}: {errors[0].message}")


async def create_study(
    session: AsyncSession, storage: StorageBackend, request: StudyCreate
) -> AnalyticalStudy:
    assay_project, question, model, prepared = await _validate_links(session, storage, request)
    if request.study_type == "INPUT_DEGRADATION_LIMIT":
        design = validate_input_degradation_limit_design(
            request.assignments, _reference_level(request)
        )
    elif request.study_type == "PAIRED_BRIDGING":
        reference, comparator = _bridge_conditions(request)
        design = validate_paired_bridging_design(request.assignments, reference, comparator)
    elif request.study_type == "ROBUSTNESS_INTERFERENCE":
        reference, challenge = _bridge_conditions(request)
        design = validate_robustness_interference_design(request.assignments, reference, challenge)
    else:
        design = validate_precision_design(request.assignments, request.factors)
    study_id = new_id()
    spec = _build_spec(study_id, request, assay_project, model, design)
    _validate_contract(spec)
    study = AnalyticalStudy(
        id=study_id,
        assay_project_id=assay_project.id,
        question_id=question.id,
        model_id=model.id,
        prepared_dataset_id=request.prepared_dataset_id,
        name=request.name,
        study_type=request.study_type,
        objective=request.objective,
        status="DESIGN_VALID" if design["valid"] else "DESIGN_INVALID",
        study_spec_json=spec,
        assignments_json=[item.model_dump(mode="json") for item in request.assignments],
        criteria_json=[item.model_dump(mode="json") for item in request.criteria],
        design_validation_json=design,
        current_revision=1,
        created_by="local-user",
    )
    session.add(study)
    await session.flush()
    session.add_all(
        [
            StudyInput(
                study_id=study.id,
                input_type="LOCKED_MODEL",
                object_id=model.id,
                role="endpoint",
                sha256=model.model_manifest_sha256,
                metadata_json={"status": "LOCKED", "model_sha256": model.model_object_sha256},
            ),
            StudyInput(
                study_id=study.id,
                input_type="EXPRESSION_BUNDLE",
                object_id=request.prepared_dataset_id,
                role="validation",
                sha256=_sha(storage.read_bytes(prepared.bundle_uri)),
                metadata_json={},
            ),
        ]
    )
    _add_criteria(session, study)
    await add_audit_event(
        session,
        assay_project,
        "ANALYTICAL_STUDY_CREATED",
        "AnalyticalStudy",
        study.id,
        revision=1,
        details={"study_type": study.study_type, "design_valid": design["valid"]},
    )
    await session.commit()
    await session.refresh(study)
    return study


def _add_criteria(session: AsyncSession, study: AnalyticalStudy) -> None:
    for item in study.criteria_json:
        session.add(
            AcceptanceCriterion(
                study_id=study.id,
                key=item["key"],
                metric=item["metric"],
                endpoint=item["endpoint"],
                operator=item["operator"],
                threshold_json=item["threshold"],
                rationale=item["rationale"],
                result_status="NOT_EVALUATED",
            )
        )


async def update_study(
    session: AsyncSession,
    storage: StorageBackend,
    study: AnalyticalStudy,
    request: StudyUpdate,
) -> AnalyticalStudy:
    if study.status not in EDITABLE_STATUSES:
        raise StudyError("A locked StudySpec is immutable; clone it to make changes.")
    payload = request.model_dump(exclude_unset=True, mode="json")
    current = StudyCreate(
        assay_project_id=study.assay_project_id,
        question_id=study.question_id,
        model_id=study.model_id,
        prepared_dataset_id=study.prepared_dataset_id,
        name=payload.get("name", study.name),
        objective=payload.get("objective", study.objective),
        study_type=study.study_type,
        assignments=payload.get("assignments", study.assignments_json),
        factors=payload.get("factors", [item["name"] for item in study.study_spec_json["factors"]]),
        criteria=payload.get("criteria", study.criteria_json),
        confidence_level=payload.get(
            "confidence_level", study.study_spec_json["analysis_plan"]["confidence_level"]
        ),
        bootstrap_iterations=payload.get(
            "bootstrap_iterations",
            study.study_spec_json["analysis_plan"].get("bootstrap_iterations", 2000),
        ),
        threshold_proximity_band=payload.get(
            "threshold_proximity_band",
            study.study_spec_json["analysis_plan"].get("threshold_proximity_band", 0.1),
        ),
        reference_level=payload.get(
            "reference_level", study.study_spec_json["analysis_plan"].get("reference_level")
        ),
        level_rationale=payload.get(
            "level_rationale", study.study_spec_json["analysis_plan"].get("level_rationale")
        ),
        reference_condition=payload.get(
            "reference_condition",
            study.study_spec_json["analysis_plan"].get("reference_condition"),
        ),
        comparator_condition=payload.get(
            "comparator_condition",
            study.study_spec_json["analysis_plan"].get("comparator_condition")
            or study.study_spec_json["analysis_plan"].get("challenge_condition"),
        ),
        equivalence_margin=payload.get(
            "equivalence_margin",
            study.study_spec_json["analysis_plan"].get("equivalence_margin")
            or study.study_spec_json["analysis_plan"].get("maximum_effect_margin"),
        ),
        condition_rationale=payload.get(
            "condition_rationale",
            study.study_spec_json["analysis_plan"].get("condition_rationale"),
        ),
    )
    assay_project, _, model, _ = await _validate_links(session, storage, current)
    if current.study_type == "INPUT_DEGRADATION_LIMIT":
        design = validate_input_degradation_limit_design(
            current.assignments, _reference_level(current)
        )
    elif current.study_type == "PAIRED_BRIDGING":
        reference, comparator = _bridge_conditions(current)
        design = validate_paired_bridging_design(current.assignments, reference, comparator)
    elif current.study_type == "ROBUSTNESS_INTERFERENCE":
        reference, challenge = _bridge_conditions(current)
        design = validate_robustness_interference_design(current.assignments, reference, challenge)
    else:
        design = validate_precision_design(current.assignments, current.factors)
    spec = _build_spec(study.id, current, assay_project, model, design)
    _validate_contract(spec)
    study.name = current.name
    study.objective = current.objective
    study.assignments_json = [item.model_dump(mode="json") for item in current.assignments]
    study.criteria_json = [item.model_dump(mode="json") for item in current.criteria]
    study.design_validation_json = design
    study.study_spec_json = spec
    study.status = "DESIGN_VALID" if design["valid"] else "DESIGN_INVALID"
    await session.execute(
        delete(AcceptanceCriterion).where(AcceptanceCriterion.study_id == study.id)
    )
    _add_criteria(session, study)
    await add_audit_event(
        session,
        assay_project,
        "ANALYTICAL_STUDY_DESIGN_VALIDATED",
        "AnalyticalStudy",
        study.id,
        revision=study.current_revision,
        details={"valid": design["valid"], "updated": True},
    )
    await session.commit()
    await session.refresh(study)
    return study


def _assignment_tsv(assignments: list[dict[str, Any]]) -> bytes:
    output = StringIO(newline="")
    writer = csv.DictWriter(
        output, fieldnames=list(assignments[0]), delimiter="\t", lineterminator="\n"
    )
    writer.writeheader()
    for assignment in assignments:
        writer.writerow(
            {
                key: "true"
                if value is True
                else "false"
                if value is False
                else ""
                if value is None
                else value
                for key, value in assignment.items()
            }
        )
    return output.getvalue().encode()


async def lock_study(
    session: AsyncSession, storage: StorageBackend, study: AnalyticalStudy
) -> AnalyticalStudy:
    if study.status not in EDITABLE_STATUSES:
        raise StudyError("Only an editable StudySpec revision can be locked.")
    if not study.design_validation_json or not study.design_validation_json["valid"]:
        raise StudyError("Design validation has blocking errors; repair the study first.")
    _validate_contract(study.study_spec_json)
    model = await session.get(ModelRecord, study.model_id)
    if model is None or model.status != "LOCKED":
        raise StudyError("The endpoint model is no longer LOCKED.")
    integrity = await model_service.integrity(session, storage, model)
    if not integrity.valid:
        raise StudyError("The locked model failed its integrity check.")
    spec_bytes = json.dumps(study.study_spec_json, indent=2, sort_keys=True).encode() + b"\n"
    assignments_bytes = _assignment_tsv(study.assignments_json)
    namespace = (
        "assay_projects",
        study.assay_project_id,
        "studies",
        study.id,
        f"revision_{study.current_revision}",
    )
    spec_object = storage.put(namespace, "study_spec.json", BytesIO(spec_bytes))
    assignments_object = storage.put(namespace, "study_assignments.tsv", BytesIO(assignments_bytes))
    study.study_spec_uri = spec_object.uri
    study.study_spec_sha256 = spec_object.sha256
    study.assignments_uri = assignments_object.uri
    study.assignments_sha256 = assignments_object.sha256
    study.status = "LOCKED"
    study.locked_at = utc_now()
    assay_project = await session.get(AssayDevelopmentProject, study.assay_project_id)
    if assay_project is None:
        raise StudyError("Assay project not found.")
    await add_audit_event(
        session,
        assay_project,
        "ANALYTICAL_STUDY_LOCKED",
        "AnalyticalStudy",
        study.id,
        revision=study.current_revision,
        hashes={
            "study_spec_sha256": spec_object.sha256,
            "assignments_sha256": assignments_object.sha256,
            "model_manifest_sha256": model.model_manifest_sha256 or "",
        },
    )
    try:
        await session.commit()
    except Exception:
        storage.delete(spec_object.uri)
        storage.delete(assignments_object.uri)
        raise
    await session.refresh(study)
    return study


async def create_study_run(
    session: AsyncSession,
    storage: StorageBackend,
    study: AnalyticalStudy,
    *,
    profile: str,
) -> Run:
    if study.status != "LOCKED":
        raise StudyError("Lock a valid StudySpec revision before running it.")
    if not study.study_spec_uri or not study.assignments_uri:
        raise StudyError("The locked study is missing immutable inputs.")
    active = await session.scalar(
        select(Run.id).where(Run.study_id == study.id, Run.state.in_(ACTIVE_STATES))
    )
    if active is not None:
        raise StudyError("This analytical study already has an active run.")
    prepared = await session.get(PreparedDataset, study.prepared_dataset_id)
    model = await session.get(ModelRecord, study.model_id)
    if prepared is None or prepared.preparation_run_id is None or model is None:
        raise StudyError("Study input lineage is incomplete.")
    integrity = await model_service.integrity(session, storage, model)
    if model.status != "LOCKED" or not integrity.valid:
        raise StudyError("The locked model failed the execution-time integrity check.")
    bundle_artifact = await session.scalar(
        select(Artifact).where(
            Artifact.run_id == prepared.preparation_run_id,
            Artifact.artifact_type == "expression_bundle",
        )
    )
    if bundle_artifact is None:
        raise StudyError("Expression Bundle checksum artifact is unavailable.")
    run_id = new_id()
    frozen = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "run_type": RunType.ASSAY_STUDY.value,
        "study_id": study.id,
        "revision": study.current_revision,
        "study_spec": {"storage_uri": study.study_spec_uri, "sha256": study.study_spec_sha256},
        "study_assignments": {
            "storage_uri": study.assignments_uri,
            "sha256": study.assignments_sha256,
        },
        "expression_bundle": {
            "prepared_dataset_id": prepared.id,
            "storage_uri": prepared.bundle_uri,
            "sha256": bundle_artifact.sha256,
        },
        "model": {
            "model_id": model.id,
            "storage_uri": model.model_uri,
            "sha256": model.model_object_sha256,
        },
        "model_manifest": {
            "storage_uri": model.model_manifest_uri,
            "sha256": model.model_manifest_sha256,
        },
    }
    stored = storage.put(
        ("runs", run_id, "inputs"),
        "assay-study-params.json",
        BytesIO((json.dumps(frozen, indent=2, sort_keys=True) + "\n").encode()),
    )
    run = Run(
        id=run_id,
        run_type=RunType.ASSAY_STUDY.value,
        prepared_dataset_id=prepared.id,
        study_id=study.id,
        state=RunState.QUEUED.value,
        profile=profile,
        params_uri=stored.uri,
        output_uri=f"run://{run_id}/output",
        work_uri=f"run://{run_id}/work",
    )
    study.status = "QUEUED"
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def clone_study(session: AsyncSession, source: AnalyticalStudy) -> AnalyticalStudy:
    clone_id = new_id()
    spec = json.loads(json.dumps(source.study_spec_json))
    spec["study"].update({"study_id": clone_id, "name": f"{source.name} (clone)", "revision": 1})
    clone = AnalyticalStudy(
        id=clone_id,
        assay_project_id=source.assay_project_id,
        question_id=source.question_id,
        model_id=source.model_id,
        prepared_dataset_id=source.prepared_dataset_id,
        parent_study_id=source.id,
        name=f"{source.name} (clone)",
        study_type=source.study_type,
        objective=source.objective,
        status=(
            "DESIGN_VALID"
            if source.design_validation_json and source.design_validation_json.get("valid")
            else "DESIGN_INVALID"
        ),
        study_spec_json=spec,
        assignments_json=json.loads(json.dumps(source.assignments_json)),
        criteria_json=json.loads(json.dumps(source.criteria_json)),
        design_validation_json=json.loads(json.dumps(source.design_validation_json or {})),
        current_revision=1,
        created_by="local-user",
    )
    session.add(clone)
    await session.flush()
    _add_criteria(session, clone)
    await session.commit()
    await session.refresh(clone)
    return clone


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
