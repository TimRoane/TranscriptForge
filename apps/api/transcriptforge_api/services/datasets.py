"""Dataset persistence operations."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api.models import Dataset, DatasetFile
from transcriptforge_api.schemas.datasets import DatasetCreate, DatasetFileRole, DatasetUpdate
from transcriptforge_api.storage.base import StoredObject


async def create_dataset(
    session: AsyncSession, project_id: str, request: DatasetCreate
) -> Dataset:
    dataset = Dataset(
        project_id=project_id,
        name=request.name,
        description=request.description,
        modality=request.modality.value,
        source_kind=request.source_kind.value,
        organism=request.organism,
        genome_build=request.genome_build,
        annotation_release=request.annotation_release,
    )
    session.add(dataset)
    await session.commit()
    await session.refresh(dataset)
    return dataset


async def list_datasets(session: AsyncSession, project_id: str) -> list[Dataset]:
    result = await session.scalars(
        select(Dataset)
        .where(Dataset.project_id == project_id)
        .order_by(Dataset.created_at.desc())
    )
    return list(result)


async def get_dataset(session: AsyncSession, dataset_id: str) -> Dataset | None:
    return await session.get(Dataset, dataset_id)


async def list_dataset_files(session: AsyncSession, dataset_id: str) -> list[DatasetFile]:
    result = await session.scalars(
        select(DatasetFile)
        .where(DatasetFile.dataset_id == dataset_id)
        .order_by(DatasetFile.created_at.desc(), DatasetFile.id.desc())
    )
    return list(result)


async def project_dataset_upload_bytes(session: AsyncSession, project_id: str) -> int:
    """Return persisted dataset-input bytes charged to the project's upload budget."""
    total = await session.scalar(
        select(func.coalesce(func.sum(DatasetFile.size_bytes), 0))
        .join(Dataset, Dataset.id == DatasetFile.dataset_id)
        .where(Dataset.project_id == project_id)
    )
    return int(total or 0)


async def update_dataset(
    session: AsyncSession, dataset: Dataset, request: DatasetUpdate
) -> Dataset:
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(dataset, field, value)
    await session.commit()
    await session.refresh(dataset)
    return dataset


async def delete_dataset(session: AsyncSession, dataset: Dataset) -> None:
    await session.delete(dataset)
    await session.commit()


async def create_dataset_file(
    session: AsyncSession,
    dataset_id: str,
    role: DatasetFileRole,
    original_name: str,
    stored: StoredObject,
) -> DatasetFile:
    dataset_file = DatasetFile(
        dataset_id=dataset_id,
        role=role.value,
        original_name=original_name,
        storage_uri=stored.uri,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
    )
    session.add(dataset_file)
    await session.commit()
    await session.refresh(dataset_file)
    return dataset_file
