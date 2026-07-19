"""Atomic, namespace-confined local filesystem storage."""

import hashlib
import os
import re
import shutil
import time
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from transcriptforge_api.storage.base import (
    InvalidStoragePathError,
    StoredObject,
)

SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
CHUNK_SIZE = 1024 * 1024


class LocalStorage:
    """Store objects beneath one configured root using generated keys."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(
        self, namespace: tuple[str, ...], original_name: str, source: BinaryIO
    ) -> StoredObject:
        directory = self._namespace_path(namespace)
        directory.mkdir(parents=True, exist_ok=True)
        suffix = self._safe_suffix(original_name)
        object_name = f"{uuid4().hex}{suffix}"
        target = directory / object_name
        temporary = directory / f".{object_name}.tmp"
        digest = hashlib.sha256()
        size_bytes = 0

        try:
            with temporary.open("xb") as destination:
                while chunk := source.read(CHUNK_SIZE):
                    digest.update(chunk)
                    size_bytes += len(chunk)
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

        relative = target.relative_to(self.root).as_posix()
        return StoredObject(
            uri=f"local://{relative}", size_bytes=size_bytes, sha256=digest.hexdigest()
        )

    def delete(self, uri: str) -> None:
        self._uri_path(uri).unlink(missing_ok=True)

    def read_bytes(self, uri: str) -> bytes:
        return self._uri_path(uri).read_bytes()

    def download(self, uri: str, destination: BinaryIO) -> None:
        with self._uri_path(uri).open("rb") as source:
            shutil.copyfileobj(source, destination, length=CHUNK_SIZE)

    def path_for(self, uri: str) -> str:
        return str(self._uri_path(uri))

    def cleanup_stale_temporary_files(self, retention_seconds: int) -> int:
        """Remove abandoned atomic-write files older than the safe retention window."""
        cutoff = time.time() - retention_seconds
        removed = 0
        for candidate in self.root.rglob(".*.tmp"):
            try:
                if candidate.is_file() and candidate.stat().st_mtime <= cutoff:
                    candidate.unlink()
                    removed += 1
            except FileNotFoundError:
                continue
        return removed

    def _namespace_path(self, namespace: tuple[str, ...]) -> Path:
        if not namespace or any(not SAFE_COMPONENT.fullmatch(part) for part in namespace):
            raise InvalidStoragePathError("Storage namespace contains an unsafe component.")
        directory = self.root.joinpath(*namespace).resolve()
        if not directory.is_relative_to(self.root):
            raise InvalidStoragePathError("Storage namespace escapes its configured root.")
        return directory

    def _uri_path(self, uri: str) -> Path:
        if not uri.startswith("local://"):
            raise InvalidStoragePathError("Expected a local storage URI.")
        relative = uri.removeprefix("local://")
        if not relative or Path(relative).is_absolute():
            raise InvalidStoragePathError("Local storage URI is invalid.")
        resolved = (self.root / relative).resolve()
        if not resolved.is_relative_to(self.root):
            raise InvalidStoragePathError("Local storage URI escapes its configured root.")
        return resolved

    @staticmethod
    def _safe_suffix(original_name: str) -> str:
        basename = Path(original_name).name
        suffixes = Path(basename).suffixes[-2:]
        suffix = "".join(suffixes)
        return suffix if len(suffix) <= 20 and re.fullmatch(r"(?:\.[A-Za-z0-9]+)*", suffix) else ""
