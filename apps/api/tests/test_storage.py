"""Local storage confinement and atomic-object tests."""

from io import BytesIO
from pathlib import Path

import pytest
from transcriptforge_api.storage.base import InvalidStoragePathError
from transcriptforge_api.storage.local import LocalStorage


def test_local_storage_rejects_unsafe_namespaces(storage: LocalStorage) -> None:
    with pytest.raises(InvalidStoragePathError):
        storage.put(("projects", "..", "outside"), "counts.tsv", BytesIO(b"data"))


def test_local_storage_rejects_escaping_uri(storage: LocalStorage) -> None:
    with pytest.raises(InvalidStoragePathError):
        storage.path_for("local://../../etc/passwd")


def test_local_storage_uses_generated_key(storage: LocalStorage) -> None:
    stored = storage.put(("projects", "safe-id"), "../../metadata.tsv.gz", BytesIO(b"abc"))
    path = Path(storage.path_for(stored.uri))

    assert path.name.endswith(".tsv.gz")
    assert "metadata" not in path.name
    assert path.read_bytes() == b"abc"
    assert storage.read_bytes(stored.uri) == b"abc"
    downloaded = BytesIO()
    storage.download(stored.uri, downloaded)
    assert downloaded.getvalue() == b"abc"
