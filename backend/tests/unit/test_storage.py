from datetime import timedelta
from io import BytesIO
from unittest.mock import ANY, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.core.storage import LocalDiskStorage, S3CompatibleStorage


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


async def test_local_storage_check_creates_root(tmp_path) -> None:
    root = tmp_path / "media"
    storage = LocalDiskStorage(root)

    await storage.check()

    assert root.is_dir()


async def test_s3_presign_uses_public_endpoint_without_network() -> None:
    internal = MagicMock()
    public = MagicMock()
    public.generate_presigned_url.return_value = (
        "https://familyos.example.test:9443/familyos-media/object"
        "?X-Amz-Signature=signature"
    )

    with patch("app.core.storage.boto3.client", side_effect=[internal, public]) as factory:
        storage = S3CompatibleStorage(
            internal_endpoint="http://object-storage:8333",
            public_endpoint="https://familyos.example.test:9443",
            access_key="familyos",
            secret_key="test-only-secret",
            bucket="familyos-media",
        )
        url = await storage.presign_put(
            "household/media/2026/09/asset/original.jpg",
            expires=timedelta(minutes=5),
        )

    assert url.startswith("https://familyos.example.test:9443/")
    assert "X-Amz-Signature=" in url
    public.generate_presigned_url.assert_called_once_with(
        "put_object",
        Params={
            "Bucket": "familyos-media",
            "Key": "household/media/2026/09/asset/original.jpg",
        },
        ExpiresIn=300,
    )
    factory.assert_any_call(
        "s3",
        endpoint_url="http://object-storage:8333",
        aws_access_key_id="familyos",
        aws_secret_access_key="test-only-secret",
        region_name="us-east-1",
        config=ANY,
    )


async def test_s3_check_and_object_operations_use_internal_endpoint() -> None:
    internal = MagicMock()
    internal.head_object.return_value = {"ContentLength": 14, "ETag": '"etag"'}
    body = BytesIO(b"family capture")
    internal.get_object.return_value = {"Body": body}

    with patch("app.core.storage.boto3.client", side_effect=[internal, MagicMock()]):
        storage = S3CompatibleStorage(
            internal_endpoint="http://object-storage:8333",
            public_endpoint="http://localhost:8333",
            access_key="familyos",
            secret_key="test-only-secret",
            bucket="familyos-media",
        )
        await storage.check()
        result = await storage.stat("household/media/original.txt")
        payload = await storage.get("household/media/original.txt")
        await storage.put(
            "household/media/original.txt",
            BytesIO(payload),
            size=len(payload),
            content_type="text/plain",
        )
        await storage.delete("household/media/original.txt")

    internal.head_bucket.assert_called_once_with(Bucket="familyos-media")
    internal.head_object.assert_called_once_with(
        Bucket="familyos-media",
        Key="household/media/original.txt",
    )
    internal.get_object.assert_called_once_with(
        Bucket="familyos-media",
        Key="household/media/original.txt",
    )
    internal.put_object.assert_called_once()
    internal.delete_object.assert_called_once_with(
        Bucket="familyos-media",
        Key="household/media/original.txt",
    )
    assert result is not None and result.size == 14 and result.etag == '"etag"'
    assert payload == b"family capture"
    assert body.closed


async def test_s3_stat_returns_none_for_missing_object() -> None:
    internal = MagicMock()
    internal.head_object.side_effect = ClientError(
        {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
        "HeadObject",
    )

    with patch("app.core.storage.boto3.client", side_effect=[internal, MagicMock()]):
        storage = S3CompatibleStorage(
            internal_endpoint="http://object-storage:8333",
            public_endpoint="http://localhost:8333",
            access_key="familyos",
            secret_key="test-only-secret",
            bucket="familyos-media",
        )
        result = await storage.stat("missing.txt")

    assert result is None


@pytest.mark.parametrize(
    "endpoint",
    ["object-storage:8333", "ftp://object-storage:8333", "http://s3/path", "http://s3?x=1"],
)
async def test_s3_client_rejects_non_origin_endpoints(endpoint: str) -> None:
    with pytest.raises(ValueError, match="absolute HTTP or HTTPS origin"):
        S3CompatibleStorage(
            internal_endpoint=endpoint,
            public_endpoint="http://localhost:8333",
            access_key="familyos",
            secret_key="test-only-secret",
            bucket="familyos-media",
        )