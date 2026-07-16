"""S3-compatible immutable object storage."""

import hashlib
import re
from pathlib import Path, PurePosixPath
from tempfile import SpooledTemporaryFile
from typing import Any, BinaryIO
from urllib.parse import urlparse
from uuid import uuid4

from transcriptforge_api.storage.base import InvalidStoragePathError, StoredObject

SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
CHUNK_SIZE = 1024 * 1024


class S3Storage:
    """Store generated immutable object keys in an S3-compatible bucket."""

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = "us-east-1",
        client: Any | None = None,
    ) -> None:
        if not bucket or "/" in bucket:
            raise ValueError("An S3 bucket name is required.")
        self.bucket = bucket
        if client is None:
            import boto3  # type: ignore[import-untyped]

            client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
            )
        self.client = client

    def put(
        self, namespace: tuple[str, ...], original_name: str, source: BinaryIO
    ) -> StoredObject:
        self._validate_namespace(namespace)
        suffix = self._safe_suffix(original_name)
        key = PurePosixPath(*namespace, f"{uuid4().hex}{suffix}").as_posix()
        digest = hashlib.sha256()
        size_bytes = 0

        with SpooledTemporaryFile(max_size=64 * CHUNK_SIZE, mode="w+b") as buffered:
            while chunk := source.read(CHUNK_SIZE):
                digest.update(chunk)
                size_bytes += len(chunk)
                buffered.write(chunk)
            buffered.seek(0)
            self.client.upload_fileobj(
                buffered,
                self.bucket,
                key,
                ExtraArgs={
                    "Metadata": {"sha256": digest.hexdigest()},
                    "ContentType": "application/octet-stream",
                },
            )

        return StoredObject(
            uri=f"s3://{self.bucket}/{key}",
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
        )

    def delete(self, uri: str) -> None:
        key = self._key_from_uri(uri)
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def read_bytes(self, uri: str) -> bytes:
        key = self._key_from_uri(uri)
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return bytes(response["Body"].read())

    def download(self, uri: str, destination: BinaryIO) -> None:
        key = self._key_from_uri(uri)
        self.client.download_fileobj(self.bucket, key, destination)

    @staticmethod
    def _validate_namespace(namespace: tuple[str, ...]) -> None:
        if not namespace or any(not SAFE_COMPONENT.fullmatch(part) for part in namespace):
            raise InvalidStoragePathError("Storage namespace contains an unsafe component.")

    def _key_from_uri(self, uri: str) -> str:
        parsed = urlparse(uri)
        if parsed.scheme != "s3" or parsed.netloc != self.bucket:
            raise InvalidStoragePathError("S3 storage URI does not belong to this bucket.")
        key = parsed.path.removeprefix("/")
        parts = PurePosixPath(key).parts
        if not key or any(part in {"", ".", ".."} for part in parts):
            raise InvalidStoragePathError("S3 storage URI is invalid.")
        return key

    @staticmethod
    def _safe_suffix(original_name: str) -> str:
        basename = Path(original_name).name
        suffix = "".join(Path(basename).suffixes[-2:])
        return suffix if len(suffix) <= 20 and re.fullmatch(r"(?:\.[A-Za-z0-9]+)*", suffix) else ""
