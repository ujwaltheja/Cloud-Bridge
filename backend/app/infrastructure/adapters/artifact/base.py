"""
ArtifactStore Port (Interface)

This is a key abstraction for the "Artifact storage (MinIO)" priority decided in PR 1.

All code that needs to store or retrieve large binary artifacts (metadata packages,
deployment zips, logs, etc.) should depend on this interface only.
"""

from abc import ABC, abstractmethod
from typing import BinaryIO


class ArtifactStore(ABC):
    """Abstract port for artifact storage."""

    @abstractmethod
    async def save(self, key: str, data: bytes | BinaryIO, content_type: str = "application/octet-stream") -> str:
        """Save data and return the storage key (or URI)."""
        ...

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """Retrieve data by key."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete an artifact."""
        ...

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if an artifact exists."""
        ...
