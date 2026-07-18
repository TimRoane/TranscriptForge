"""Health endpoint schemas."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Stable liveness response for clients and container health checks."""

    status: Literal["ok"]
    service: Literal["transcriptforge-api"]
    version: str
    environment: str
    deployment_mode: Literal["single_user_local"]


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    database: Literal["ok"]


class SystemCapabilitiesResponse(BaseModel):
    deployment_mode: Literal["single_user_local"]
    authentication_enabled: Literal[False]
    max_upload_bytes: int
    project_upload_quota_bytes: int
