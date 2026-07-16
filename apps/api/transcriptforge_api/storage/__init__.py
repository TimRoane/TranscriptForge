"""Artifact and upload storage adapters."""

from functools import lru_cache

from transcriptforge_api.config import get_settings
from transcriptforge_api.storage.base import StorageBackend
from transcriptforge_api.storage.local import LocalStorage
from transcriptforge_api.storage.s3 import S3Storage


@lru_cache
def get_storage_backend() -> StorageBackend:
    settings = get_settings()
    if settings.storage_backend == "local":
        return LocalStorage(settings.local_storage_root)
    if settings.storage_backend in {"s3", "minio"}:
        return S3Storage(
            settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
        )
    raise RuntimeError(f"Storage backend '{settings.storage_backend}' is not supported.")
