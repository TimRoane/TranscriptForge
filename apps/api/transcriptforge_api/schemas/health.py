"""Health endpoint schemas."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Stable liveness response for clients and container health checks."""

    status: Literal["ok"]
    service: Literal["transcriptforge-api"]
    version: str
    environment: str
