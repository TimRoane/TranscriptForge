"""Service liveness routes."""

from fastapi import APIRouter

from transcriptforge_api import __version__
from transcriptforge_api.config import get_settings
from transcriptforge_api.schemas.health import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report process liveness without depending on downstream services."""
    return HealthResponse(
        status="ok",
        service="transcriptforge-api",
        version=__version__,
        environment=get_settings().environment,
    )
