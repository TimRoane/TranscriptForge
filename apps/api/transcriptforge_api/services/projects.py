"""Project persistence operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api.models import Project
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
    await session.delete(project)
    await session.commit()
