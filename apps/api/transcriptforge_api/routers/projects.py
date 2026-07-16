"""Project CRUD routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api.db.session import get_session
from transcriptforge_api.models import Project
from transcriptforge_api.schemas.projects import ProjectCreate, ProjectRead, ProjectUpdate
from transcriptforge_api.services import projects as project_service

router = APIRouter(prefix="/projects", tags=["projects"])
Session = Annotated[AsyncSession, Depends(get_session)]


async def require_project(session: AsyncSession, project_id: str) -> Project:
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(request: ProjectCreate, session: Session) -> Project:
    return await project_service.create_project(session, request)


@router.get("", response_model=list[ProjectRead])
async def list_projects(session: Session) -> list[Project]:
    return await project_service.list_projects(session)


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: str, session: Session) -> Project:
    return await require_project(session, project_id)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(project_id: str, request: ProjectUpdate, session: Session) -> Project:
    project = await require_project(session, project_id)
    return await project_service.update_project(session, project, request)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: str, session: Session) -> Response:
    project = await require_project(session, project_id)
    await project_service.delete_project(session, project)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
