"""Storage interface and immutable object metadata."""

from dataclasses import dataclass
from typing import BinaryIO, Protocol


@dataclass(frozen=True, slots=True)
class StoredObject:
    uri: str
    size_bytes: int
    sha256: str


class StorageBackend(Protocol):
    def put(
        self, namespace: tuple[str, ...], original_name: str, source: BinaryIO
    ) -> StoredObject: ...

    def delete(self, uri: str) -> None: ...

    def read_bytes(self, uri: str) -> bytes: ...

    def download(self, uri: str, destination: BinaryIO) -> None: ...

class InvalidStoragePathError(ValueError):
    """Raised when a storage namespace or URI escapes its allowed root."""
