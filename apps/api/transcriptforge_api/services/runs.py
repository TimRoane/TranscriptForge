"""Durable validation-run creation and query operations."""

import json
from io import BytesIO
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api.models import Artifact, Dataset, DatasetFile, PreparedDataset, Run
from transcriptforge_api.models.base import new_id
from transcriptforge_api.models.enums import DatasetStatus, RunState, RunType
from transcriptforge_api.schemas.runs import DatasetValidationRequest
from transcriptforge_api.services.microarray import (
    MicroarrayIngestionError,
    load_platform_adapter,
)
from transcriptforge_api.services.raw_rnaseq import RawRNASeqIngestionError, load_reference_bundle
from transcriptforge_api.storage.base import StorageBackend

ACTIVE_STATES = (
    RunState.CREATED.value,
    RunState.QUEUED.value,
    RunState.STARTING.value,
    RunState.RUNNING.value,
)


class ValidationInputError(ValueError):
    """Raised when a dataset is not ready to enter matrix validation."""


async def create_validation_run(
    session: AsyncSession,
    storage: StorageBackend,
    dataset: Dataset,
    request: DatasetValidationRequest,
    *,
    profile: str,
) -> Run:
    if dataset.source_kind not in {"count_matrix", "normalized_matrix"}:
        raise ValidationInputError("Only count and normalized matrices can use matrix validation.")

    active = await session.scalar(
        select(Run.id).where(
            Run.dataset_id == dataset.id,
            Run.run_type == RunType.DATASET_VALIDATION.value,
            Run.state.in_(ACTIVE_STATES),
        )
    )
    if active is not None:
        raise ValidationInputError("This dataset already has an active validation run.")

    matrix_role = "count_matrix" if dataset.source_kind == "count_matrix" else "expression_matrix"
    files = await _latest_files(session, dataset.id, (matrix_role, "sample_metadata"))
    missing = [role for role in (matrix_role, "sample_metadata") if role not in files]
    if missing:
        raise ValidationInputError(
            "Upload the required files before validation: " + ", ".join(missing) + "."
        )

    run_id = new_id()
    frozen: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "run_type": RunType.DATASET_VALIDATION.value,
        "dataset": {
            "id": dataset.id,
            "name": dataset.name,
            "modality": dataset.modality,
            "source_kind": dataset.source_kind,
            "organism": dataset.organism,
            "genome_build": dataset.genome_build,
            "annotation_release": dataset.annotation_release,
            "status_before_validation": dataset.status,
        },
        "inputs": {
            role: {
                "dataset_file_id": item.id,
                "original_name": item.original_name,
                "storage_uri": item.storage_uri,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
            }
            for role, item in files.items()
        },
        "validation": request.model_dump(),
    }
    payload = (json.dumps(frozen, indent=2, sort_keys=True) + "\n").encode()
    stored = storage.put(
        ("projects", dataset.project_id, "datasets", dataset.id, "runs", run_id, "inputs"),
        "validation-params.json",
        BytesIO(payload),
    )
    run = Run(
        id=run_id,
        run_type=RunType.DATASET_VALIDATION.value,
        dataset_id=dataset.id,
        state=RunState.QUEUED.value,
        profile=profile,
        params_uri=stored.uri,
        output_uri=f"run://{run_id}/output",
        work_uri=f"run://{run_id}/work",
    )
    dataset.status = DatasetStatus.VALIDATING.value
    session.add(run)
    try:
        await session.commit()
    except Exception:
        storage.delete(stored.uri)
        raise
    await session.refresh(run)
    return run


async def create_preparation_run(
    session: AsyncSession,
    storage: StorageBackend,
    dataset: Dataset,
    *,
    profile: str,
) -> Run:
    if dataset.status not in {DatasetStatus.VALID.value, DatasetStatus.PREPARED.value}:
        raise ValidationInputError("Validate the current dataset inputs before preparation.")
    active = await session.scalar(
        select(Run.id).where(
            Run.dataset_id == dataset.id,
            Run.run_type == RunType.DATASET_PREPARATION.value,
            Run.state.in_(ACTIVE_STATES),
        )
    )
    if active is not None:
        raise ValidationInputError("This dataset already has an active preparation run.")
    next_version = int(
        (
            await session.scalar(
                select(func.max(PreparedDataset.version)).where(
                    PreparedDataset.dataset_id == dataset.id
                )
            )
        )
        or 0
    ) + 1
    run_id = new_id()
    prepared_dataset_id = new_id()
    if dataset.source_kind == "fastq":
        manifest_file = (await _latest_files(session, dataset.id, ("raw_ingestion_manifest",))).get(
            "raw_ingestion_manifest"
        )
        if manifest_file is None:
            raise ValidationInputError("Validate the current raw RNA-seq sample sheet first.")
        ingestion = json.loads(storage.read_bytes(manifest_file.storage_uri))
        try:
            reference, definition_sha256 = load_reference_bundle(
                str(ingestion["reference"]["reference_id"])
            )
        except RawRNASeqIngestionError as error:
            raise ValidationInputError(
                "The pinned reference is no longer available; re-ingest before quantification."
            ) from error
        if definition_sha256 != ingestion["reference"]["definition_sha256"]:
            raise ValidationInputError(
                "The pinned reference definition changed; re-ingest before quantification."
            )
        frozen = {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "run_type": RunType.DATASET_PREPARATION.value,
            "prepared_dataset_id": prepared_dataset_id,
            "prepared_version": next_version,
            "dataset": {
                "id": dataset.id,
                "name": dataset.name,
                "modality": dataset.modality,
                "source_kind": dataset.source_kind,
                "organism": dataset.organism,
                "genome_build": dataset.genome_build,
                "annotation_release": dataset.annotation_release,
                "status_before_validation": dataset.status,
            },
            "inputs": {
                "raw_ingestion_manifest": {
                    "dataset_file_id": manifest_file.id,
                    "original_name": manifest_file.original_name,
                    "storage_uri": manifest_file.storage_uri,
                    "size_bytes": manifest_file.size_bytes,
                    "sha256": manifest_file.sha256,
                }
            },
            "raw_ingestion": ingestion,
            "reference": {
                "reference_id": reference["reference_id"],
                "definition_sha256": definition_sha256,
            },
        }
    elif dataset.source_kind == "affymetrix_cel":
        manifest_file = (
            await _latest_files(session, dataset.id, ("microarray_ingestion_manifest",))
        ).get("microarray_ingestion_manifest")
        if manifest_file is None:
            raise ValidationInputError("Validate the current Affymetrix CEL inputs first.")
        ingestion = json.loads(storage.read_bytes(manifest_file.storage_uri))
        try:
            platform, definition_sha256 = load_platform_adapter(
                str(ingestion["platform"]["platform_id"])
            )
        except (KeyError, MicroarrayIngestionError) as error:
            raise ValidationInputError(
                "The pinned microarray platform is unavailable; re-ingest before RMA."
            ) from error
        if definition_sha256 != ingestion["platform"]["definition_sha256"]:
            raise ValidationInputError(
                "The pinned microarray platform definition changed; re-ingest before RMA."
            )
        frozen = {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "run_type": RunType.DATASET_PREPARATION.value,
            "prepared_dataset_id": prepared_dataset_id,
            "prepared_version": next_version,
            "dataset": {
                "id": dataset.id,
                "name": dataset.name,
                "modality": dataset.modality,
                "source_kind": dataset.source_kind,
                "organism": dataset.organism,
                "genome_build": dataset.genome_build,
                "annotation_release": dataset.annotation_release,
                "status_before_validation": dataset.status,
            },
            "inputs": {
                "microarray_ingestion_manifest": {
                    "dataset_file_id": manifest_file.id,
                    "original_name": manifest_file.original_name,
                    "storage_uri": manifest_file.storage_uri,
                    "size_bytes": manifest_file.size_bytes,
                    "sha256": manifest_file.sha256,
                }
            },
            "microarray_ingestion": ingestion,
            "platform": {
                "platform_id": platform["platform_id"],
                "definition_sha256": definition_sha256,
            },
        }
    else:
        validation_run = await session.scalar(
            select(Run)
            .where(
                Run.dataset_id == dataset.id,
                Run.run_type == RunType.DATASET_VALIDATION.value,
                Run.state == RunState.SUCCEEDED.value,
            )
            .order_by(Run.created_at.desc())
            .limit(1)
        )
        if validation_run is None:
            raise ValidationInputError("No successful validation run is available for preparation.")
        validated = json.loads(storage.read_bytes(validation_run.params_uri))
        frozen = {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "run_type": RunType.DATASET_PREPARATION.value,
            "prepared_dataset_id": prepared_dataset_id,
            "prepared_version": next_version,
            "dataset": {
                **validated["dataset"],
                "status_before_validation": dataset.status,
            },
            "inputs": validated["inputs"],
            "validation": validated["validation"],
            "source_validation_run_id": validation_run.id,
        }
    payload = (json.dumps(frozen, indent=2, sort_keys=True) + "\n").encode()
    stored = storage.put(
        ("projects", dataset.project_id, "datasets", dataset.id, "runs", run_id, "inputs"),
        "preparation-params.json",
        BytesIO(payload),
    )
    run = Run(
        id=run_id,
        run_type=RunType.DATASET_PREPARATION.value,
        dataset_id=dataset.id,
        state=RunState.QUEUED.value,
        profile=profile,
        params_uri=stored.uri,
        output_uri=f"run://{run_id}/output",
        work_uri=f"run://{run_id}/work",
    )
    dataset.status = DatasetStatus.PREPARING.value
    session.add(run)
    try:
        await session.commit()
    except Exception:
        storage.delete(stored.uri)
        raise
    await session.refresh(run)
    return run


async def _latest_files(
    session: AsyncSession, dataset_id: str, roles: tuple[str, ...]
) -> dict[str, DatasetFile]:
    result = await session.scalars(
        select(DatasetFile)
        .where(DatasetFile.dataset_id == dataset_id, DatasetFile.role.in_(roles))
        .order_by(DatasetFile.created_at.desc(), DatasetFile.id.desc())
    )
    latest: dict[str, DatasetFile] = {}
    for item in result:
        latest.setdefault(item.role, item)
    return latest


async def get_run(session: AsyncSession, run_id: str) -> Run | None:
    return await session.get(Run, run_id)


async def list_validation_runs(
    session: AsyncSession, dataset_id: str, *, limit: int = 10
) -> list[Run]:
    result = await session.scalars(
        select(Run)
        .where(
            Run.dataset_id == dataset_id,
            Run.run_type == RunType.DATASET_VALIDATION.value,
        )
        .order_by(Run.created_at.desc())
        .limit(limit)
    )
    return list(result)


async def list_preparation_runs(
    session: AsyncSession, dataset_id: str, *, limit: int = 10
) -> list[Run]:
    result = await session.scalars(
        select(Run)
        .where(
            Run.dataset_id == dataset_id,
            Run.run_type == RunType.DATASET_PREPARATION.value,
        )
        .order_by(Run.created_at.desc())
        .limit(limit)
    )
    return list(result)


async def list_prepared_datasets(
    session: AsyncSession, dataset_id: str
) -> list[PreparedDataset]:
    result = await session.scalars(
        select(PreparedDataset)
        .where(PreparedDataset.dataset_id == dataset_id)
        .order_by(PreparedDataset.version.desc())
    )
    return list(result)


async def get_prepared_dataset(
    session: AsyncSession, prepared_dataset_id: str
) -> PreparedDataset | None:
    return await session.get(PreparedDataset, prepared_dataset_id)


async def list_artifacts(session: AsyncSession, run_id: str) -> list[Artifact]:
    result = await session.scalars(
        select(Artifact)
        .where(Artifact.run_id == run_id)
        .order_by(Artifact.display_order, Artifact.title)
    )
    return list(result)


async def get_artifact(session: AsyncSession, artifact_id: str) -> Artifact | None:
    return await session.get(Artifact, artifact_id)


async def get_artifact_by_type(
    session: AsyncSession, run_id: str, artifact_type: str
) -> Artifact | None:
    return cast(
        Artifact | None,
        await session.scalar(
            select(Artifact).where(
                Artifact.run_id == run_id, Artifact.artifact_type == artifact_type
            )
        ),
    )
