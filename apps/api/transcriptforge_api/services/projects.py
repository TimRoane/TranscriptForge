"""Project persistence operations."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api.models import (
    AnalyticalStudy,
    AssayDevelopmentProject,
    ExperimentPlan,
    GuidanceResult,
    Project,
)
from transcriptforge_api.schemas.projects import ProjectCreate, ProjectUpdate


async def create_project(session: AsyncSession, request: ProjectCreate) -> Project:
    project = Project(name=request.name, description=request.description)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def list_projects(session: AsyncSession) -> list[Project]:
    result = await session.scalars(select(Project).order_by(Project.created_at.desc()))
    return list(result)


async def get_project(session: AsyncSession, project_id: str) -> Project | None:
    return await session.get(Project, project_id)


async def update_project(
    session: AsyncSession, project: Project, request: ProjectUpdate
) -> Project:
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await session.commit()
    await session.refresh(project)
    return project


async def delete_project(session: AsyncSession, project: Project) -> None:
    # These lifecycle records deliberately RESTRICT deletion of their immutable
    # prepared/model/question inputs. Delete the project-owned dependants first;
    # otherwise PostgreSQL may evaluate the dataset cascade before the parallel
    # assay-project cascade and reject an otherwise valid whole-project delete.
    assay_ids = select(AssayDevelopmentProject.id).where(
        AssayDevelopmentProject.project_id == project.id
    )
    for model in (GuidanceResult, AnalyticalStudy, ExperimentPlan):
        await session.execute(delete(model).where(model.assay_project_id.in_(assay_ids)))
    await session.flush()
    await session.delete(project)
    await session.commit()
