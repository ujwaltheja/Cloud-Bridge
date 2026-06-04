"""
LocalFilesystemArtifactStore - Default implementation for development.

Stores artifacts on the local filesystem (or Docker volume).
"""

from pathlib import Path
from typing import BinaryIO

from .base import ArtifactStore


class LocalFilesystemArtifactStore(ArtifactStore):
    """
    Stores artifacts under a configured base directory.
    Simple and sufficient for PR 1 + early development.
    """

    def __init__(self, base_path: str = "/app/artifacts"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_path(self, key: str) -> Path:
        # Prevent path traversal
        safe_key = key.replace("..", "").lstrip("/")
        return self.base_path / safe_key

    async def save(self, key: str, data: bytes | BinaryIO, content_type: str = "application/octet-stream") -> str:
        path = self._get_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            with open(path, "wb") as f:
                f.write(data.read() if hasattr(data, "read") else data)

        return str(path)

    async def get(self, key: str) -> bytes:
        path = self._get_path(key)
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {key}")
        return path.read_bytes()

    async def delete(self, key: str) -> None:
        path = self._get_path(key)
        if path.exists():
            path.unlink()

    async def exists(self, key: str) -> bool:
        return self._get_path(key).exists()
