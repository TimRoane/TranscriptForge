"""S3-compatible storage contract tests without a network dependency."""

from io import BytesIO
from typing import Any, BinaryIO

import pytest
from transcriptforge_api.storage.base import InvalidStoragePathError
from transcriptforge_api.storage.s3 import S3Storage


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.extra_args: dict[str, Any] | None = None

    def upload_fileobj(
        self, source: BinaryIO, bucket: str, key: str, ExtraArgs: dict[str, Any]
    ) -> None:
        self.objects[(bucket, key)] = source.read()
        self.extra_args = ExtraArgs

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.objects.pop((Bucket, Key), None)

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, BytesIO]:
        return {"Body": BytesIO(self.objects[(Bucket, Key)])}

    def download_fileobj(self, bucket: str, key: str, destination: BinaryIO) -> None:
        destination.write(self.objects[(bucket, key)])


def test_s3_storage_uploads_hashed_generated_object() -> None:
    client = FakeS3Client()
    storage = S3Storage("transcriptforge", client=client)

    stored = storage.put(
        ("projects", "project-id", "inputs"), "../../counts.tsv.gz", BytesIO(b"abc")
    )

    key = stored.uri.removeprefix("s3://transcriptforge/")
    assert key.startswith("projects/project-id/inputs/")
    assert key.endswith(".tsv.gz")
    assert "counts" not in key
    assert client.objects[("transcriptforge", key)] == b"abc"
    assert client.extra_args == {
        "Metadata": {"sha256": stored.sha256},
        "ContentType": "application/octet-stream",
    }
    assert storage.read_bytes(stored.uri) == b"abc"
    downloaded = BytesIO()
    storage.download(stored.uri, downloaded)
    assert downloaded.getvalue() == b"abc"

    storage.delete(stored.uri)
    assert client.objects == {}


def test_s3_storage_rejects_foreign_bucket_and_traversal() -> None:
    storage = S3Storage("transcriptforge", client=FakeS3Client())
    with pytest.raises(InvalidStoragePathError):
        storage.delete("s3://other-bucket/projects/id/file.tsv")
    with pytest.raises(InvalidStoragePathError):
        storage.put(("projects", ".."), "file.tsv", BytesIO(b"abc"))
