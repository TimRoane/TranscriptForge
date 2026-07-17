"""Saved analysis configuration and immutable analysis-run operations."""

import json
from io import BytesIO
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api.models import (
    Analysis,
    Artifact,
    Dataset,
    PreparedDataset,
    Run,
    SignatureMapping,
)
from transcriptforge_api.models.base import new_id
from transcriptforge_api.models.enums import AnalysisType, RunState, RunType
from transcriptforge_api.schemas.analyses import (
    AnalysisCreate,
    DifferentialExpressionParameters,
    DifferentialExpressionPreviewRequest,
    DimensionReductionParameters,
    SignatureScoringParameters,
)
from transcriptforge_api.services.design_validation import validate_design
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
    dataset = await session.get(Dataset, prepared.dataset_id)
    if dataset is None:
        raise AnalysisInputError("The source dataset no longer exists.")
    configuration = request.model_dump(mode="json", exclude={"name", "description"})
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
    analysis = Analysis(
        project_id=dataset.project_id,
        prepared_dataset_id=prepared.id,
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
    if analysis.analysis_type == AnalysisType.DIFFERENTIAL_EXPRESSION.value:
        frozen.update(
            design_formula=configuration["design_formula"],
            contrast_label=configuration["contrast_label"],
            design_validation=configuration["design_validation"],
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
