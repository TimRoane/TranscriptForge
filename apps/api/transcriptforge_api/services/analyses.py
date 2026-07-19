"""Saved analysis configuration and immutable analysis-run operations."""

import json
from io import BytesIO
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api.models import (
    Analysis,
    Artifact,
    AssayDevelopmentProject,
    Dataset,
    PreparedDataset,
    Run,
    ScientificQuestion,
    SignatureMapping,
)
from transcriptforge_api.models.base import new_id
from transcriptforge_api.models.enums import AnalysisType, RunState, RunType
from transcriptforge_api.schemas.analyses import (
    AnalysisCreate,
    ClassifierParameters,
    ClassifierPreviewRequest,
    DeconvolutionParameters,
    DifferentialExpressionParameters,
    DifferentialExpressionPreviewRequest,
    DimensionReductionParameters,
    MetadataVariableRead,
    PhenotypeAssociationParameters,
    SignatureScoringParameters,
)
from transcriptforge_api.services.classifier_design import validate_classifier_design
from transcriptforge_api.services.deconvolution import (
    method_registry,
    validate_saved_configuration,
)
from transcriptforge_api.services.design_validation import design_options, validate_design
from transcriptforge_api.services.guided_assay import get_question_catalog
from transcriptforge_api.services.runs import ACTIVE_STATES
from transcriptforge_api.storage.base import StorageBackend


class AnalysisInputError(ValueError):
    """Raised when an analysis cannot be saved or launched."""


async def create_analysis(
    session: AsyncSession,
    storage: StorageBackend,
    prepared: PreparedDataset,
    request: AnalysisCreate,
) -> Analysis:
    if bool(request.assay_project_id) != bool(request.scientific_question_id):
        raise AnalysisInputError(
            "Guided analyses require both an assay project and a scientific question."
        )
    if request.assay not in prepared.value_types_available:
        available = ", ".join(prepared.value_types_available)
        raise AnalysisInputError(
            f"Assay '{request.assay}' is not available in this bundle. Available: {available}."
        )
    if request.analysis_type == AnalysisType.DIMENSION_REDUCTION:
        if not isinstance(request.parameters, DimensionReductionParameters):
            raise AnalysisInputError("Dimension-reduction parameters are invalid.")
        if request.method == "hierarchical_clustering" and (
            request.parameters.cluster_count > prepared.sample_count
        ):
            raise AnalysisInputError("Cluster count cannot exceed the number of samples.")
        if request.method == "umap" and request.parameters.neighbors >= prepared.sample_count:
            raise AnalysisInputError("UMAP neighbors must be smaller than the number of samples.")
        if request.method == "tsne" and request.parameters.perplexity >= prepared.sample_count:
            raise AnalysisInputError("t-SNE perplexity must be smaller than the number of samples.")
    elif request.analysis_type == AnalysisType.SIGNATURE:
        if not isinstance(request.parameters, SignatureScoringParameters):
            raise AnalysisInputError("Signature-scoring parameters are invalid.")
        if request.assay != "log_expression":
            raise AnalysisInputError(
                "Signature scoring currently requires the log_expression assay."
            )
        if request.method in {"mean_z_score", "gsva", "ssgsea"} and prepared.sample_count < 2:
            raise AnalysisInputError(
                f"{request.method} signature scoring requires at least two samples."
            )
    elif request.analysis_type == AnalysisType.DECONVOLUTION and not isinstance(
        request.parameters, DeconvolutionParameters
    ):
        raise AnalysisInputError("Deconvolution parameters are invalid.")
    elif request.analysis_type == AnalysisType.CLASSIFIER:
        if not isinstance(request.parameters, ClassifierParameters):
            raise AnalysisInputError("Classifier parameters are invalid.")
        if request.assay != "log_expression":
            raise AnalysisInputError(
                "Binary classifier development currently requires the log_expression assay."
            )
    dataset = await session.get(Dataset, prepared.dataset_id)
    if dataset is None:
        raise AnalysisInputError("The source dataset no longer exists.")
    guided_project: AssayDevelopmentProject | None = None
    guided_question: ScientificQuestion | None = None
    if request.assay_project_id and request.scientific_question_id:
        guided_project = await session.get(AssayDevelopmentProject, request.assay_project_id)
        guided_question = await session.get(ScientificQuestion, request.scientific_question_id)
        if guided_project is None or guided_project.project_id != dataset.project_id:
            raise AnalysisInputError(
                "The guided assay workspace does not belong to this prepared dataset's project."
            )
        if guided_question is None or guided_question.assay_project_id != guided_project.id:
            raise AnalysisInputError("The scientific question does not belong to this workspace.")
        route = next(
            (
                item
                for item in get_question_catalog().questions
                if item.key == guided_question.question_key
            ),
            None,
        )
        if route is None or route.analysis_type != request.analysis_type.value:
            expected = route.analysis_type if route is not None else None
            raise AnalysisInputError(
                f"This question routes to '{expected or 'no analysis'}', not "
                f"'{request.analysis_type.value}'."
            )
    configuration = request.model_dump(
        mode="json",
        exclude={"name", "description", "assay_project_id", "scientific_question_id"},
    )
    if request.analysis_type == AnalysisType.DECONVOLUTION:
        assert isinstance(request.parameters, DeconvolutionParameters)
        registry, method_spec, assay_descriptor, reference_profile = validate_saved_configuration(
            prepared,
            storage,
            method_id=str(request.method),
            assay_name=request.assay,
            reference_profile=request.parameters.reference_profile,
            minimum_gene_overlap=request.parameters.minimum_gene_overlap,
        )
        parameters = dict(configuration["parameters"])
        parameters["reference_profile"] = reference_profile
        configuration["parameters"] = parameters
        configuration["method_registry_version"] = registry.registry_version
        configuration["method_registry_sha256"] = registry.registry_sha256
        configuration["method_spec"] = method_spec.model_dump(mode="json")
        configuration["input_assay_descriptor"] = assay_descriptor
        configuration["result_type"] = method_spec.result_type
        configuration["execution_available"] = method_spec.implementation_status == "available"
    if request.analysis_type == AnalysisType.SIGNATURE:
        assert isinstance(request.parameters, SignatureScoringParameters)
        mapping = await session.get(SignatureMapping, request.parameters.signature_mapping_id)
        if mapping is None or mapping.prepared_dataset_id != prepared.id:
            raise AnalysisInputError(
                "The signature mapping does not belong to this prepared dataset."
            )
        if any(item["mapped_identifier_count"] == 0 for item in mapping.report_json["sets"]):
            raise AnalysisInputError(
                "Every signature set requires at least one mapped feature before scoring."
            )
        if request.method == "weighted_linear" and any(
            "weight" not in entry
            for item in mapping.report_json["sets"]
            for entry in item["mapped_entries"]
        ):
            raise AnalysisInputError(
                "Weighted linear scoring requires a weight for every mapped identifier."
            )
        if request.method in {"gsva", "ssgsea"}:
            invalid_sets = [
                item["name"]
                for item in mapping.report_json["sets"]
                if not (
                    request.parameters.minimum_gene_set_size
                    <= item["mapped_identifier_count"]
                    <= request.parameters.maximum_gene_set_size
                )
            ]
            if invalid_sets:
                raise AnalysisInputError(
                    "Mapped gene-set sizes fall outside the configured minimum/maximum: "
                    + ", ".join(invalid_sets[:10])
                    + ("." if len(invalid_sets) <= 10 else ", …")
                )
        association = request.parameters.phenotype_association
        if association.enabled:
            rows, options = design_options(prepared, storage)
            known = {variable.name: variable for variable in options.variables}
            requested_columns = [
                association.phenotype_column,
                *association.covariates,
                association.block_column,
            ]
            for column in (item for item in requested_columns if item is not None):
                variable = known.get(column)
                if variable is None:
                    raise AnalysisInputError(
                        f"Association variable '{column}' is not present in sample metadata."
                    )
                if variable.missing_count:
                    raise AnalysisInputError(
                        f"Association variable '{column}' contains missing values."
                    )
                if variable.unique_count < 2:
                    raise AnalysisInputError(
                        f"Association variable '{column}' has only one observed value."
                    )
            phenotype = known[str(association.phenotype_column)]
            if association.phenotype_kind != "auto" and (
                phenotype.kind != association.phenotype_kind
            ):
                raise AnalysisInputError(
                    f"Phenotype '{phenotype.name}' is {phenotype.kind}, not "
                    f"{association.phenotype_kind}."
                )
            _validate_association_design(rows, known, association)
        configuration["signature_mapping_report_sha256"] = mapping.report_sha256
        configuration["signature_definition_id"] = mapping.signature_definition_id
        configuration["mapping_coverage"] = mapping.mapping_coverage
    if request.analysis_type == AnalysisType.DIFFERENTIAL_EXPRESSION:
        if not isinstance(request.parameters, DifferentialExpressionParameters):
            raise AnalysisInputError("Differential-expression parameters are invalid.")
        preview = validate_design(
            prepared,
            storage,
            DifferentialExpressionPreviewRequest(
                assay=request.assay,
                method=request.method,
                parameters=request.parameters,
            ),
        )
        if not preview.valid:
            raise AnalysisInputError(" ".join(preview.errors))
        configuration["method"] = preview.resolved_method
        configuration["design_formula"] = preview.formula
        configuration["contrast_label"] = preview.contrast_label
        configuration["design_validation"] = preview.model_dump(mode="json")
    if request.analysis_type == AnalysisType.CLASSIFIER:
        assert isinstance(request.parameters, ClassifierParameters)
        classifier_preview = validate_classifier_design(
            prepared,
            storage,
            ClassifierPreviewRequest(
                assay="log_expression",
                method=request.method,
                parameters=request.parameters,
                random_seed=request.random_seed,
            ),
        )
        if not classifier_preview.valid:
            raise AnalysisInputError(" ".join(classifier_preview.errors))
        configuration["design_validation"] = classifier_preview.model_dump(mode="json")
        configuration["execution_available"] = True
        configuration["leakage_policy"] = {
            "preprocessing_scope": "fit_inside_each_training_fold",
            "feature_selection_scope": "fit_inside_each_training_fold",
            "hyperparameter_tuning_scope": "inner_training_folds_only",
            "outer_test_fold_role": "evaluation_only",
        }
    analysis = Analysis(
        project_id=dataset.project_id,
        prepared_dataset_id=prepared.id,
        assay_project_id=guided_project.id if guided_project else None,
        scientific_question_id=guided_question.id if guided_question else None,
        analysis_type=request.analysis_type.value,
        name=request.name,
        description=request.description,
        configuration_json=configuration,
    )
    session.add(analysis)
    await session.commit()
    await session.refresh(analysis)
    return analysis


async def get_analysis(session: AsyncSession, analysis_id: str) -> Analysis | None:
    return await session.get(Analysis, analysis_id)


async def list_analyses(session: AsyncSession, prepared_dataset_id: str) -> list[Analysis]:
    result = await session.scalars(
        select(Analysis)
        .where(Analysis.prepared_dataset_id == prepared_dataset_id)
        .order_by(Analysis.created_at.desc())
    )
    return list(result)


async def list_analysis_runs(session: AsyncSession, analysis_id: str) -> list[Run]:
    result = await session.scalars(
        select(Run)
        .where(Run.analysis_id == analysis_id, Run.run_type == RunType.ANALYSIS.value)
        .order_by(Run.created_at.desc())
    )
    return list(result)


async def clone_analysis(session: AsyncSession, source: Analysis) -> Analysis:
    clone = Analysis(
        project_id=source.project_id,
        prepared_dataset_id=source.prepared_dataset_id,
        assay_project_id=source.assay_project_id,
        scientific_question_id=source.scientific_question_id,
        analysis_type=source.analysis_type,
        name=f"{source.name} (copy)",
        description=source.description,
        configuration_json=source.configuration_json,
    )
    session.add(clone)
    await session.commit()
    await session.refresh(clone)
    return clone


async def create_analysis_run(
    session: AsyncSession,
    storage: StorageBackend,
    analysis: Analysis,
    *,
    profile: str,
) -> Run:
    if analysis.analysis_type == AnalysisType.DECONVOLUTION.value:
        registry = method_registry()
        method_id = str(analysis.configuration_json.get("method", ""))
        method = next((item for item in registry.methods if item.id == method_id), None)
        if (
            method is None
            or method.implementation_status != "available"
            or method.execution_mode != "native"
        ):
            raise AnalysisInputError(
                "This deconvolution analysis does not have a native scientific runner. The "
                "selected method may be external-import-only or require a future implementation "
                "or separate upstream license acceptance and installation."
            )
    active = await session.scalar(
        select(Run.id).where(
            Run.analysis_id == analysis.id,
            Run.run_type == RunType.ANALYSIS.value,
            Run.state.in_(ACTIVE_STATES),
        )
    )
    if active is not None:
        raise AnalysisInputError("This analysis already has an active run.")
    prepared = await session.get(PreparedDataset, analysis.prepared_dataset_id)
    if prepared is None:
        raise AnalysisInputError("The prepared dataset no longer exists.")
    bundle_artifact = await session.scalar(
        select(Artifact).where(
            Artifact.run_id == prepared.preparation_run_id,
            Artifact.artifact_type == "expression_bundle",
        )
    )
    if bundle_artifact is None:
        raise AnalysisInputError("The prepared Expression Bundle is not available.")

    run_id = new_id()
    configuration: dict[str, Any] = dict(analysis.configuration_json)
    frozen = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "run_type": RunType.ANALYSIS.value,
        "analysis_id": analysis.id,
        "prepared_dataset_id": prepared.id,
        "analysis_type": analysis.analysis_type,
        "method": configuration["method"],
        "assay": configuration["assay"],
        "parameters": configuration["parameters"],
        "random_seed": configuration["random_seed"],
        "expression_bundle": {
            "storage_uri": prepared.bundle_uri,
            "sha256": bundle_artifact.sha256,
            "size_bytes": bundle_artifact.size_bytes,
        },
    }
    if analysis.assay_project_id and analysis.scientific_question_id:
        question = await session.get(ScientificQuestion, analysis.scientific_question_id)
        if question is None or question.assay_project_id != analysis.assay_project_id:
            raise AnalysisInputError("The guided scientific question is no longer available.")
        frozen["guided_context"] = {
            "assay_project_id": analysis.assay_project_id,
            "scientific_question_id": question.id,
            "question_key": question.question_key,
            "question": question.plain_language_question,
            "formal_question": question.formal_question,
        }
    if analysis.analysis_type == AnalysisType.SIGNATURE.value:
        parameters = configuration["parameters"]
        mapping = await session.get(SignatureMapping, parameters["signature_mapping_id"])
        if mapping is None or mapping.prepared_dataset_id != prepared.id:
            raise AnalysisInputError("The frozen signature mapping is unavailable.")
        if mapping.report_sha256 != configuration["signature_mapping_report_sha256"]:
            raise AnalysisInputError("The frozen signature mapping checksum changed.")
        if mapping.report_json["expression_bundle_sha256"] != bundle_artifact.sha256:
            raise AnalysisInputError(
                "The signature mapping was produced from a different Expression Bundle."
            )
        frozen["signature_mapping"] = {
            "id": mapping.id,
            "report_sha256": mapping.report_sha256,
            "report": mapping.report_json,
        }
    if analysis.analysis_type == AnalysisType.DECONVOLUTION.value:
        frozen["deconvolution_method"] = configuration["method_spec"]
        frozen["method_registry_version"] = configuration["method_registry_version"]
        frozen["method_registry_sha256"] = configuration["method_registry_sha256"]
        frozen["input_assay_descriptor"] = configuration["input_assay_descriptor"]
    if analysis.analysis_type == AnalysisType.DIFFERENTIAL_EXPRESSION.value:
        frozen.update(
            design_formula=configuration["design_formula"],
            contrast_label=configuration["contrast_label"],
            design_validation=configuration["design_validation"],
        )
    if analysis.analysis_type == AnalysisType.CLASSIFIER.value:
        frozen.update(
            design_validation=configuration["design_validation"],
            leakage_policy=configuration["leakage_policy"],
        )
    payload = (json.dumps(frozen, indent=2, sort_keys=True) + "\n").encode()
    stored = storage.put(
        (
            "projects",
            analysis.project_id,
            "analyses",
            analysis.id,
            "runs",
            run_id,
            "inputs",
        ),
        "analysis-request.json",
        BytesIO(payload),
    )
    run = Run(
        id=run_id,
        run_type=RunType.ANALYSIS.value,
        dataset_id=prepared.dataset_id,
        prepared_dataset_id=prepared.id,
        analysis_id=analysis.id,
        state=RunState.QUEUED.value,
        profile=profile,
        params_uri=stored.uri,
        output_uri=f"run://{run_id}/output",
        work_uri=f"run://{run_id}/work",
    )
    session.add(run)
    try:
        await session.commit()
    except Exception:
        storage.delete(stored.uri)
        raise
    await session.refresh(run)
    return run


def _validate_association_design(
    rows: list[dict[str, str]],
    known: dict[str, MetadataVariableRead],
    association: PhenotypeAssociationParameters,
) -> None:
    columns = [np.ones(len(rows), dtype=np.float64)]
    terms = [*association.covariates]
    if association.block_column:
        terms.append(association.block_column)
    assert association.phenotype_column is not None
    terms.append(association.phenotype_column)
    for term in terms:
        values = [row[term].strip() for row in rows]
        variable = known[term]
        kind = variable.kind
        if term == association.block_column:
            kind = "categorical"
        if term == association.phenotype_column and association.phenotype_kind != "auto":
            kind = association.phenotype_kind
        if kind == "numeric":
            numeric = np.asarray([float(value) for value in values], dtype=np.float64)
            columns.append(numeric - np.mean(numeric))
        else:
            levels = sorted(set(values))
            if term == association.phenotype_column and any(
                values.count(level) < 2 for level in levels
            ):
                raise AnalysisInputError(
                    f"Phenotype '{term}' requires at least two samples in every group."
                )
            columns.extend(
                np.asarray([value == level for value in values], dtype=np.float64)
                for level in levels[1:]
            )
    matrix = np.column_stack(columns)
    rank = int(np.linalg.matrix_rank(matrix))
    if rank < matrix.shape[1]:
        raise AnalysisInputError(
            "The phenotype association design is rank deficient. Remove confounded or "
            "redundant covariates/block terms."
        )
    if matrix.shape[1] >= len(rows):
        raise AnalysisInputError(
            "The phenotype association design has no residual degrees of freedom. "
            "Remove adjustment terms or add samples."
        )
