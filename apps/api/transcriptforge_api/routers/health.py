"""Service liveness routes."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from transcriptforge_api import __version__
from transcriptforge_api.config import get_settings
from transcriptforge_api.db.session import get_session
from transcriptforge_api.observability import api_metrics
from transcriptforge_api.schemas.health import (
    HealthResponse,
    ReadinessResponse,
    SystemCapabilitiesResponse,
)

router = APIRouter(tags=["system"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report process liveness without depending on downstream services."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service="transcriptforge-api",
        version=__version__,
        environment=settings.environment,
        deployment_mode=settings.deployment_mode,
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(session: Session) -> ReadinessResponse:
    """Report readiness only after the relational control plane responds."""
    await session.execute(text("SELECT 1"))
    return ReadinessResponse(status="ready", database="ok")


@router.get("/system", response_model=SystemCapabilitiesResponse)
async def system_capabilities() -> SystemCapabilitiesResponse:
    """Expose the explicit deployment boundary and configured upload budgets."""
    settings = get_settings()
    return SystemCapabilitiesResponse(
        deployment_mode=settings.deployment_mode,
        authentication_enabled=False,
        max_upload_bytes=settings.max_upload_bytes,
        project_upload_quota_bytes=settings.project_upload_quota_bytes,
    )


@router.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
async def metrics() -> PlainTextResponse:
    """Publish low-cardinality process metrics without request or research payloads."""
    return PlainTextResponse(api_metrics.render(), media_type="text/plain; version=0.0.4")
