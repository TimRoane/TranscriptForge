"""Typed application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration shared by API and worker processes."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="TRANSCRIPTFORGE_",
        extra="ignore",
    )

    environment: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = "postgresql+asyncpg://transcriptforge:transcriptforge@localhost:5432/transcriptforge"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    storage_backend: str = "local"
    local_storage_root: Path = Path(".transcriptforge-data")
    run_work_root: Path = Path(".transcriptforge-runs")
    reference_cache_root: Path = Path(".transcriptforge-reference-cache")
    pipeline_path: Path = Path("pipelines/main.nf")
    nextflow_executable: str = "nextflow"
    nextflow_profile: str = "test"
    aws_work_uri: str | None = None
    s3_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str = "transcriptforge"
    s3_region: str = "us-east-1"
    cors_origins: list[AnyHttpUrl] = Field(default_factory=lambda: [AnyHttpUrl("http://localhost:5173")])


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-by-convention settings instance per process."""
    return Settings()
