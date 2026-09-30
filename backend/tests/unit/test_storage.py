from datetime import timedelta
from io import BytesIO

import pytest

from app.core.storage import LocalDiskStorage, MinioStorage


async def test_local_storage_put_get_stat_and_delete(tmp_path) -> None:
    storage = LocalDiskStorage(tmp_path)
    payload = b"family capture"

    await storage.put(
        "household/media/original.txt",
        BytesIO(payload),
        size=len(payload),
        content_type="text/plain",
    )

    stored = await storage.stat("household/media/original.txt")
    assert stored is not None
    assert stored.size == len(payload)
    assert await storage.get("household/media/original.txt") == payload

    await storage.delete("household/media/original.txt")
    assert await storage.stat("household/media/original.txt") is None


async def test_local_storage_rejects_keys_outside_root(tmp_path) -> None:
    storage = LocalDiskStorage(tmp_path)

    with pytest.raises(ValueError, match="escapes"):
        await storage.get("../outside.txt")


async def test_minio_presign_uses_public_endpoint_without_network() -> None:
    storage = MinioStorage(
        internal_endpoint="http://minio:9000",
        public_endpoint="https://familyos.example.test:9443",
        access_key="familyos",
        secret_key="test-only-secret",
        bucket="familyos-media",
    )

    url = await storage.presign_put(
        "household/media/2026/09/asset/original.jpg",
        expires=timedelta(minutes=5),
    )

    assert url.startswith("https://familyos.example.test:9443/familyos-media/")
    assert "X-Amz-Signature=" in url