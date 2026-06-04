"""Tests for the ArtifactStore implementations (PR 1)."""

import pytest

from app.infrastructure.adapters.artifact.local import LocalFilesystemArtifactStore
from app.infrastructure.adapters.artifact.base import ArtifactStore


@pytest.fixture
def local_store(tmp_path) -> LocalFilesystemArtifactStore:
    return LocalFilesystemArtifactStore(base_path=str(tmp_path))


@pytest.mark.asyncio
async def test_local_store_save_and_get(local_store: ArtifactStore):
    key = "test/hello.txt"
    data = b"Hello from Cloud Bridge PR 1"

    saved_key = await local_store.save(key, data)
    assert "hello.txt" in saved_key

    retrieved = await local_store.get(key)
    assert retrieved == data


@pytest.mark.asyncio
async def test_local_store_exists_and_delete(local_store: ArtifactStore):
    key = "test/deleteme.bin"
    await local_store.save(key, b"delete me")

    assert await local_store.exists(key) is True

    await local_store.delete(key)
    assert await local_store.exists(key) is False
