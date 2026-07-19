"""Development Experiment persistence, design validation, lock, and launch boundary."""

import csv
import json
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from transcriptforge_analysis.assay_experiment import (
    PAIRED_CONDITION_EXPERIMENT,
    validate_input_degradation_design,
    validate_paired_condition_design,
)
from transcriptforge_analysis.multifactor_experiment import (
    MULTIFACTOR_EXPERIMENT,
    validate_multifactor_design,
)
from transcriptforge_analysis.technical_feasibility_experiment import (
    TECHNICAL_FEASIBILITY_EXPERIMENT,
    validate_technical_feasibility_design,
)

from transcriptforge_api.models import (
    Artifact,
    AssayDevelopmentProject,
    Dataset,
    ExperimentInput,
    ExperimentPlan,
    PreparedDataset,
    Run,
    ScientificQuestion,
)
from transcriptforge_api.models.base import new_id, utc_now
from transcriptforge_api.models.enums import RunState, RunType
from transcriptforge_api.schemas.experiments import (
    ExperimentAssignment,
    ExperimentCreate,
    ExperimentRead,
    ExperimentUpdate,
)
from transcriptforge_api.services.guided_assay import add_audit_event
from transcriptforge_api.storage.base import StorageBackend

EDITABLE_STATUSES = {"DRAFT", "DESIGN_VALID", "DESIGN_INVALID"}
ACTIVE_STATES = {"CREATED", "QUEUED", "STARTING", "RUNNING", "CANCELLING"}
EXPERIMENT_SCHEMA = (
    Path(__file__).resolve().parents[4] / "contracts/experiment/experiment_spec.schema.json"
)
IMPLEMENTED_EXPERIMENT_ROUTES = {
    "INPUT_DEGRADATION_EXPLORATION": "input_degradation_stability",
    PAIRED_CONDITION_EXPERIMENT: "paired_condition_performance",
    MULTIFACTOR_EXPERIMENT: "multifactor_optimization",
    TECHNICAL_FEASIBILITY_EXPERIMENT: "usable_rna_feasibility",
}


class ExperimentError(ValueError):
    """Raised when an experiment lifecycle operation is not scientifically safe."""


def experiment_read(item: ExperimentPlan) -> ExperimentRead:
    return ExperimentRead(
        id=item.id,
        assay_project_id=item.assay_project_id,
        question_id=item.question_id,
        prepared_dataset_id=item.prepared_dataset_id,
        parent_experiment_id=item.parent_experiment_id,
        name=item.name,
        experiment_type=item.experiment_type,
        objective=item.objective,
        mode=item.mode,
        status=item.status,
        experiment_spec=item.experiment_spec_json,
        experiment_spec_uri=item.experiment_spec_uri,
        experiment_spec_sha256=item.experiment_spec_sha256,
        assignments=[
            ExperimentAssignment.model_validate(assignment) for assignment in item.assignments_json
        ],
        assignments_uri=item.assignments_uri,
        assignments_sha256=item.assignments_sha256,
        design_validation=item.design_validation_json,
        development_bundle_uri=item.development_bundle_uri,
        current_revision=item.current_revision,
        created_by=item.created_by,
        created_at=item.created_at,
        updated_at=item.updated_at,
        locked_at=item.locked_at,
        completed_at=item.completed_at,
    )


async def _validate_links(
    session: AsyncSession,
    assay_project_id: str,
    question_id: str,
    prepared_dataset_id: str,
    experiment_type: str,
) -> tuple[AssayDevelopmentProject, ScientificQuestion, PreparedDataset]:
    assay_project = await session.get(AssayDevelopmentProject, assay_project_id)
    question = await session.get(ScientificQuestion, question_id)
    prepared = await session.get(PreparedDataset, prepared_dataset_id)
    if assay_project is None:
        raise ExperimentError("Assay project not found.")
    if question is None or question.assay_project_id != assay_project.id:
        raise ExperimentError("The scientific question does not belong to this assay project.")
    expected_question = IMPLEMENTED_EXPERIMENT_ROUTES.get(experiment_type)
    if expected_question is None or question.question_key != expected_question:
        raise ExperimentError(
            "The selected scientific question does not match this Development Experiment template."
        )
    if prepared is None:
        raise ExperimentError("Prepared Expression Bundle not found.")
    dataset = await session.get(Dataset, prepared.dataset_id)
    if dataset is None or dataset.project_id != assay_project.project_id:
        raise ExperimentError("The Expression Bundle does not belong to the linked base project.")
    return assay_project, question, prepared


def _build_spec(
    experiment_id: str,
    request: ExperimentCreate,
    assay_project: AssayDevelopmentProject,
    question: ScientificQuestion,
    *,
    revision: int = 1,
) -> dict[str, Any]:
    factors: list[dict[str, Any]]
    analysis_plan: dict[str, Any]
    rationales: dict[str, Any]
    if request.experiment_type == TECHNICAL_FEASIBILITY_EXPERIMENT:
        factors = [
            {"name": "specimen_group", "type": "categorical", "role": "primary"},
            {"name": "run", "type": "categorical", "role": "blocking"},
            {"name": "operator", "type": "categorical", "role": "blocking"},
        ]
        analysis_plan = {
            "template": "technical_feasibility_summary",
            "assay": request.assay,
            "confidence_level": 0.95,
            "missing_value_policy": "fail_required_endpoint",
            "failure_source": "explicit_assignment_or_nonfinite_expression",
            "criteria_mode": "exploratory",
        }
        rationales = {
            "feasibility_scope": request.condition_contrast_rationale
            or "Summarize usable measurements under the explicitly tested conditions.",
            "endpoint_choice": request.endpoint_rationale,
        }
    elif request.experiment_type == PAIRED_CONDITION_EXPERIMENT:
        factors = [
            {"name": "condition", "type": "categorical", "role": "primary"},
            {"name": "run", "type": "categorical", "role": "blocking"},
            {"name": "operator", "type": "categorical", "role": "blocking"},
            {"name": "reagent_lot", "type": "categorical", "role": "blocking"},
            {"name": "quality_metric", "type": "continuous", "role": "covariate"},
        ]
        analysis_plan = {
            "template": "paired_condition_multi_endpoint_comparison",
            "assay": request.assay,
            "reference_condition": request.reference_condition,
            "comparator_condition": request.comparator_condition,
            "confidence_level": 0.95,
            "missing_value_policy": "fail_required_endpoint",
        }
        rationales = {
            "condition_contrast": request.condition_contrast_rationale,
            "endpoint_choice": request.endpoint_rationale,
        }
    elif request.experiment_type == MULTIFACTOR_EXPERIMENT:
        numeric = {"input_ng", "dv200", "sequencing_depth"}
        factors = [
            {
                "name": factor,
                "type": "continuous" if factor in numeric else "categorical",
                "role": "primary",
            }
            for factor in request.factor_names
        ] + [{"name": "run", "type": "categorical", "role": "blocking"}]
        analysis_plan = {
            "template": "constrained_multifactor_optimization",
            "assay": request.assay,
            "factor_names": request.factor_names,
            "interactions": request.interactions,
            "confidence_level": 0.95,
            "missing_value_policy": "fail_required_endpoint",
            "maximum_primary_factors": 3,
            "maximum_interactions": 2,
            "repeated_sample_model": "biological_sample_fixed_block_with_variance_summary",
            "response_surface_policy": "only_two_numeric_factors_with_supported_design",
        }
        rationales = {
            "factor_and_interaction_choice": request.condition_contrast_rationale,
            "endpoint_choice": request.endpoint_rationale,
        }
    else:
        factors = [
            {"name": "input_ng", "type": "ordered_numeric", "role": "primary"},
            {"name": "dv200", "type": "continuous", "role": "covariate"},
            {"name": "sequencing_run", "type": "categorical", "role": "blocking"},
            {"name": "operator", "type": "categorical", "role": "blocking"},
        ]
        analysis_plan = {
            "template": "ordered_level_paired_exploration",
            "assay": request.assay,
            "reference_level": request.reference_level,
            "confidence_level": 0.95,
            "missing_value_policy": "fail_required_endpoint",
        }
        rationales = {
            "reference_level": request.reference_level_rationale,
            "endpoint_choice": request.endpoint_rationale,
        }
    return {
        "schema_version": "1.0.0",
        "experiment": {
            "experiment_id": experiment_id,
            "name": request.name,
            "type": request.experiment_type,
            "stage": question.stage,
            "objective": request.objective,
            "exploratory": True,
            "mode": request.mode,
            "revision": revision,
        },
        "assay_context": {
            "specimen_type": assay_project.specimen_type or "not_recorded",
            "proposed_output": assay_project.proposed_output or "not_recorded",
            "assay_version": assay_project.assay_version or "development-unlocked",
        },
        "question": {
            "question_key": question.question_key,
            "plain_language": question.plain_language_question,
            "decision_to_inform": question.formal_question,
        },
        "inputs": {
            "assignment_table": "design/experiment_assignments.tsv",
            "expression_bundles": [
                {"prepared_dataset_id": request.prepared_dataset_id, "role": "development"}
            ],
        },
        "sample_structure": {
            "measurement_id": "measurement_id",
            "biological_sample_id": "biological_sample_id",
            "replicate_id": "replicate_id",
            "pair_id": "biological_sample_id",
        },
        "factors": factors,
        "endpoints": {
            "primary": request.primary_endpoints,
            "secondary": request.secondary_endpoints,
        },
        "analysis_plan": analysis_plan,
        "success_guidance": {
            "mode": "exploratory",
            "declared_questions": request.declared_questions,
        },
        "rationales": rationales,
    }


def _rows_for_validator(assignments: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            key: (
                "true"
                if value is True
                else "false"
                if value is False
                else ""
                if value is None
                else str(value)
            )
            for key, value in row.items()
        }
        for row in assignments
    ]


def _validate(item: ExperimentPlan) -> dict[str, Any]:
    schema = json.loads(EXPERIMENT_SCHEMA.read_text(encoding="utf-8"))
    contract_errors = sorted(
        Draft202012Validator(schema).iter_errors(item.experiment_spec_json),
        key=lambda error: list(error.path),
    )
    if contract_errors:
        location = ".".join(str(value) for value in contract_errors[0].path) or "document"
        raise ExperimentError(
            f"ExperimentSpec is invalid at {location}: {contract_errors[0].message}"
        )
    rows = _rows_for_validator(item.assignments_json)
    if item.experiment_type == PAIRED_CONDITION_EXPERIMENT:
        return validate_paired_condition_design(item.experiment_spec_json, rows).to_dict()
    if item.experiment_type == MULTIFACTOR_EXPERIMENT:
        return validate_multifactor_design(item.experiment_spec_json, rows).to_dict()
    if item.experiment_type == TECHNICAL_FEASIBILITY_EXPERIMENT:
        return validate_technical_feasibility_design(item.experiment_spec_json, rows).to_dict()
    return validate_input_degradation_design(item.experiment_spec_json, rows).to_dict()


async def create_experiment(session: AsyncSession, request: ExperimentCreate) -> ExperimentPlan:
    assay_project, question, _ = await _validate_links(
        session,
        request.assay_project_id,
        request.question_id,
        request.prepared_dataset_id,
        request.experiment_type,
    )
    experiment_id = new_id()
    assignments = [item.model_dump(mode="json") for item in request.assignments]
    if any(item["prepared_dataset_id"] != request.prepared_dataset_id for item in assignments):
        raise ExperimentError("Every assignment must reference the selected prepared dataset.")
    experiment = ExperimentPlan(
        id=experiment_id,
        assay_project_id=assay_project.id,
        question_id=question.id,
        prepared_dataset_id=request.prepared_dataset_id,
        name=request.name,
        experiment_type=request.experiment_type,
        objective=request.objective,
        mode=request.mode,
        status="DRAFT",
        experiment_spec_json=_build_spec(experiment_id, request, assay_project, question),
        assignments_json=assignments,
        current_revision=1,
        created_by="local-user",
    )
    session.add(experiment)
    await session.flush()
    experiment.design_validation_json = _validate(experiment)
    experiment.status = (
        "DESIGN_VALID" if experiment.design_validation_json["valid"] else "DESIGN_INVALID"
    )
    session.add(
        ExperimentInput(
            experiment_id=experiment.id,
            input_type="EXPRESSION_BUNDLE",
            prepared_dataset_id=request.prepared_dataset_id,
            role="development",
            metadata_json={"assay": request.assay},
        )
    )
    await add_audit_event(
        session,
        assay_project,
        "EXPERIMENT_CREATED",
        "ExperimentPlan",
        experiment.id,
        revision=1,
        details={"experiment_type": experiment.experiment_type},
    )
    await add_audit_event(
        session,
        assay_project,
        "EXPERIMENT_DESIGN_VALIDATED",
        "ExperimentPlan",
        experiment.id,
        revision=1,
        details={"valid": experiment.design_validation_json["valid"]},
    )
    await session.commit()
    await session.refresh(experiment)
    return experiment


async def get_experiment(session: AsyncSession, experiment_id: str) -> ExperimentPlan | None:
    return await session.get(ExperimentPlan, experiment_id)


async def list_experiments(session: AsyncSession, assay_project_id: str) -> list[ExperimentPlan]:
    result = await session.scalars(
        select(ExperimentPlan)
        .where(ExperimentPlan.assay_project_id == assay_project_id)
        .order_by(ExperimentPlan.updated_at.desc())
    )
    return list(result)


async def update_experiment(
    session: AsyncSession,
    experiment: ExperimentPlan,
    request: ExperimentUpdate,
) -> ExperimentPlan:
    if experiment.status not in EDITABLE_STATUSES:
        raise ExperimentError("A locked revision is immutable; clone it to make changes.")
    values = request.model_dump(exclude_unset=True, mode="json")
    if "assignments" in values:
        if any(
            item["prepared_dataset_id"] != experiment.prepared_dataset_id
            for item in values["assignments"]
        ):
            raise ExperimentError(
                "Every assignment must reference the experiment's prepared dataset."
            )
        experiment.assignments_json = values["assignments"]
    if "name" in values:
        experiment.name = values["name"]
        experiment.experiment_spec_json["experiment"]["name"] = values["name"]
    if "objective" in values:
        experiment.objective = values["objective"]
        experiment.experiment_spec_json["experiment"]["objective"] = values["objective"]
    if "reference_level" in values:
        experiment.experiment_spec_json["analysis_plan"]["reference_level"] = values[
            "reference_level"
        ]
    if "reference_condition" in values:
        experiment.experiment_spec_json["analysis_plan"]["reference_condition"] = values[
            "reference_condition"
        ]
    if "comparator_condition" in values:
        experiment.experiment_spec_json["analysis_plan"]["comparator_condition"] = values[
            "comparator_condition"
        ]
    if "primary_endpoints" in values:
        experiment.experiment_spec_json["endpoints"]["primary"] = values["primary_endpoints"]
    if "secondary_endpoints" in values:
        experiment.experiment_spec_json["endpoints"]["secondary"] = values["secondary_endpoints"]
    if "declared_questions" in values:
        experiment.experiment_spec_json["success_guidance"]["declared_questions"] = values[
            "declared_questions"
        ]
    if "reference_level_rationale" in values:
        experiment.experiment_spec_json["rationales"]["reference_level"] = values[
            "reference_level_rationale"
        ]
    if "condition_contrast_rationale" in values:
        experiment.experiment_spec_json["rationales"]["condition_contrast"] = values[
            "condition_contrast_rationale"
        ]
    if "factor_names" in values:
        experiment.experiment_spec_json["analysis_plan"]["factor_names"] = values["factor_names"]
    if "interactions" in values:
        experiment.experiment_spec_json["analysis_plan"]["interactions"] = values["interactions"]
    if "endpoint_rationale" in values:
        experiment.experiment_spec_json["rationales"]["endpoint_choice"] = values[
            "endpoint_rationale"
        ]
    # Assign a fresh top-level object so SQLAlchemy JSON change tracking is explicit.
    experiment.experiment_spec_json = json.loads(json.dumps(experiment.experiment_spec_json))
    experiment.design_validation_json = _validate(experiment)
    experiment.status = (
        "DESIGN_VALID" if experiment.design_validation_json["valid"] else "DESIGN_INVALID"
    )
    assay_project = await session.get(AssayDevelopmentProject, experiment.assay_project_id)
    if assay_project is None:
        raise ExperimentError("Assay project not found.")
    await add_audit_event(
        session,
        assay_project,
        "EXPERIMENT_DESIGN_VALIDATED",
        "ExperimentPlan",
        experiment.id,
        revision=experiment.current_revision,
        details={"valid": experiment.design_validation_json["valid"], "updated": True},
    )
    await session.commit()
    await session.refresh(experiment)
    return experiment


async def validate_design(session: AsyncSession, experiment: ExperimentPlan) -> ExperimentPlan:
    if experiment.status not in EDITABLE_STATUSES:
        raise ExperimentError("A locked execution revision cannot be revalidated or changed.")
    experiment.design_validation_json = _validate(experiment)
    experiment.status = (
        "DESIGN_VALID" if experiment.design_validation_json["valid"] else "DESIGN_INVALID"
    )
    assay_project = await session.get(AssayDevelopmentProject, experiment.assay_project_id)
    if assay_project is None:
        raise ExperimentError("Assay project not found.")
    await add_audit_event(
        session,
        assay_project,
        "EXPERIMENT_DESIGN_VALIDATED",
        "ExperimentPlan",
        experiment.id,
        revision=experiment.current_revision,
        details={"valid": experiment.design_validation_json["valid"]},
    )
    await session.commit()
    await session.refresh(experiment)
    return experiment


def _assignment_tsv(assignments: list[dict[str, Any]]) -> bytes:
    columns = list(assignments[0])
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for assignment in assignments:
        writer.writerow(
            {
                key: (
                    "true"
                    if value is True
                    else "false"
                    if value is False
                    else ""
                    if value is None
                    else value
                )
                for key, value in assignment.items()
            }
        )
    return output.getvalue().encode()


async def lock_experiment(
    session: AsyncSession,
    storage: StorageBackend,
    experiment: ExperimentPlan,
) -> ExperimentPlan:
    if experiment.status not in EDITABLE_STATUSES:
        raise ExperimentError("Only an editable experiment revision can be locked.")
    design = _validate(experiment)
    experiment.design_validation_json = design
    if not design["valid"]:
        experiment.status = "DESIGN_INVALID"
        await session.commit()
        raise ExperimentError("Design validation has blocking errors; correct or clone the design.")
    spec_bytes = (
        json.dumps(experiment.experiment_spec_json, indent=2, sort_keys=True) + "\n"
    ).encode()
    assignment_bytes = _assignment_tsv(experiment.assignments_json)
    namespace = (
        "assay_projects",
        experiment.assay_project_id,
        "experiments",
        experiment.id,
        f"revision_{experiment.current_revision}",
    )
    spec_object = storage.put(namespace, "experiment_spec.json", BytesIO(spec_bytes))
    assignment_object = storage.put(
        namespace, "experiment_assignments.tsv", BytesIO(assignment_bytes)
    )
    experiment.experiment_spec_uri = spec_object.uri
    experiment.experiment_spec_sha256 = spec_object.sha256
    experiment.assignments_uri = assignment_object.uri
    experiment.assignments_sha256 = assignment_object.sha256
    experiment.status = "LOCKED_FOR_EXECUTION"
    experiment.locked_at = utc_now()
    assay_project = await session.get(AssayDevelopmentProject, experiment.assay_project_id)
    if assay_project is None:
        raise ExperimentError("Assay project not found.")
    await add_audit_event(
        session,
        assay_project,
        "EXPERIMENT_REVISION_LOCKED",
        "ExperimentPlan",
        experiment.id,
        revision=experiment.current_revision,
        hashes={
            "experiment_spec_sha256": spec_object.sha256,
            "assignments_sha256": assignment_object.sha256,
        },
    )
    try:
        await session.commit()
    except Exception:
        storage.delete(spec_object.uri)
        storage.delete(assignment_object.uri)
        raise
    await session.refresh(experiment)
    return experiment


async def create_experiment_run(
    session: AsyncSession,
    storage: StorageBackend,
    experiment: ExperimentPlan,
    *,
    profile: str,
) -> Run:
    if experiment.status != "LOCKED_FOR_EXECUTION":
        raise ExperimentError("Lock a valid immutable execution revision before running it.")
    if not experiment.experiment_spec_uri or not experiment.assignments_uri:
        raise ExperimentError("The locked revision is missing immutable input artifacts.")
    active = await session.scalar(
        select(Run.id).where(
            Run.experiment_id == experiment.id,
            Run.state.in_(ACTIVE_STATES),
        )
    )
    if active is not None:
        raise ExperimentError("This experiment already has an active run.")
    prepared = await session.get(PreparedDataset, experiment.prepared_dataset_id)
    if prepared is None or prepared.preparation_run_id is None:
        raise ExperimentError("Prepared Expression Bundle lineage is incomplete.")
    bundle_artifact = await session.scalar(
        select(Artifact).where(
            Artifact.run_id == prepared.preparation_run_id,
            Artifact.artifact_type == "expression_bundle",
        )
    )
    if bundle_artifact is None:
        raise ExperimentError("Expression Bundle checksum artifact is unavailable.")
    run_id = new_id()
    frozen = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "run_type": RunType.ASSAY_EXPERIMENT,
        "experiment_id": experiment.id,
        "revision": experiment.current_revision,
        "experiment_spec": {
            "storage_uri": experiment.experiment_spec_uri,
            "sha256": experiment.experiment_spec_sha256,
        },
        "experiment_assignments": {
            "storage_uri": experiment.assignments_uri,
            "sha256": experiment.assignments_sha256,
        },
        "expression_bundle": {
            "prepared_dataset_id": prepared.id,
            "storage_uri": prepared.bundle_uri,
            "sha256": bundle_artifact.sha256,
        },
    }
    stored = storage.put(
        ("runs", run_id, "inputs"),
        "assay-experiment-params.json",
        BytesIO((json.dumps(frozen, indent=2, sort_keys=True) + "\n").encode()),
    )
    run = Run(
        id=run_id,
        run_type=RunType.ASSAY_EXPERIMENT,
        prepared_dataset_id=prepared.id,
        experiment_id=experiment.id,
        state=RunState.QUEUED,
        profile=profile,
        params_uri=stored.uri,
        output_uri=f"run://{run_id}/output",
        work_uri=f"run://{run_id}/work",
    )
    experiment.status = "QUEUED"
    session.add(run)
    assay_project = await session.get(AssayDevelopmentProject, experiment.assay_project_id)
    if assay_project is None:
        raise ExperimentError("Assay project not found.")
    await add_audit_event(
        session,
        assay_project,
        "EXPERIMENT_RUN_STARTED",
        "ExperimentPlan",
        experiment.id,
        revision=experiment.current_revision,
        details={"run_id": run_id, "state": "QUEUED"},
    )
    try:
        await session.commit()
    except Exception:
        storage.delete(stored.uri)
        raise
    await session.refresh(run)
    return run


async def clone_experiment(
    session: AsyncSession, source: ExperimentPlan, *, follow_up: bool = False
) -> ExperimentPlan:
    clone_id = new_id()
    spec = json.loads(json.dumps(source.experiment_spec_json))
    spec["experiment"]["experiment_id"] = clone_id
    clone_name = f"Balanced confirmation: {source.name}" if follow_up else f"{source.name} (clone)"
    clone_objective = (
        "Prospectively review a balanced confirmation design around the candidate input levels."
        if follow_up
        else source.objective
    )
    clone_mode = "PLAN_FIRST" if follow_up else source.mode
    spec["experiment"]["name"] = clone_name
    spec["experiment"]["objective"] = clone_objective
    spec["experiment"]["mode"] = clone_mode
    spec["experiment"]["revision"] = 1
    clone = ExperimentPlan(
        id=clone_id,
        assay_project_id=source.assay_project_id,
        question_id=source.question_id,
        prepared_dataset_id=source.prepared_dataset_id,
        parent_experiment_id=source.id,
        name=clone_name,
        experiment_type=source.experiment_type,
        objective=clone_objective,
        mode=clone_mode,
        status="DRAFT",
        experiment_spec_json=spec,
        assignments_json=json.loads(json.dumps(source.assignments_json)),
        current_revision=1,
        created_by="local-user",
    )
    session.add(clone)
    await session.flush()
    clone.design_validation_json = _validate(clone)
    clone.status = "DESIGN_VALID" if clone.design_validation_json["valid"] else "DESIGN_INVALID"
    assay_project = await session.get(AssayDevelopmentProject, source.assay_project_id)
    if assay_project is None:
        raise ExperimentError("Assay project not found.")
    await add_audit_event(
        session,
        assay_project,
        "EXPERIMENT_CREATED",
        "ExperimentPlan",
        clone.id,
        revision=1,
        details={"parent_experiment_id": source.id, "follow_up": follow_up},
    )
    await session.commit()
    await session.refresh(clone)
    return clone
