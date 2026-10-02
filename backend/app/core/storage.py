import asyncio
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any, BinaryIO, Protocol
from urllib.parse import urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import Depends

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class StoredObject:
    size: int
    etag: str | None


class StorageBackend(Protocol):
    async def check(self) -> None: ...

    async def presign_put(self, key: str, *, expires: timedelta) -> str: ...

    async def stat(self, key: str) -> StoredObject | None: ...

    async def put(self, key: str, source: BinaryIO, *, size: int, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...

    async def url_for(self, key: str, *, expires: timedelta) -> str: ...


def _s3_client(endpoint: str, access_key: str, secret_key: str) -> Any:
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("S3 endpoint must be an absolute HTTP or HTTPS origin")
    return boto3.client(
        "s3",
        endpoint_url=endpoint.rstrip("/"),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )


class S3CompatibleStorage:
    def __init__(
        self,
        *,
        internal_endpoint: str,
        public_endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
    ) -> None:
        self._internal = _s3_client(internal_endpoint, access_key, secret_key)
        self._public = _s3_client(public_endpoint, access_key, secret_key)
        self._bucket = bucket

    async def check(self) -> None:
        await asyncio.to_thread(self._internal.head_bucket, Bucket=self._bucket)

    async def presign_put(self, key: str, *, expires: timedelta = timedelta(minutes=10)) -> str:
        return await asyncio.to_thread(
            self._public.generate_presigned_url,
            "put_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=int(expires.total_seconds()),
        )

    async def stat(self, key: str) -> StoredObject | None:
        try:
            result = await asyncio.to_thread(
                self._internal.head_object,
                Bucket=self._bucket,
                Key=key,
            )
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")
            status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in {"404", "NoSuchKey", "NoSuchObject", "NotFound"} or status == 404:
                return None
            raise
        return StoredObject(size=result["ContentLength"], etag=result.get("ETag"))

    async def put(self, key: str, source: BinaryIO, *, size: int, content_type: str) -> None:
        await asyncio.to_thread(
            self._internal.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=source,
            ContentLength=size,
            ContentType=content_type,
        )

    async def get(self, key: str) -> bytes:
        response = await asyncio.to_thread(
            self._internal.get_object,
            Bucket=self._bucket,
            Key=key,
        )
        body = response["Body"]
        try:
            return await asyncio.to_thread(body.read)
        finally:
            await asyncio.to_thread(body.close)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(
            self._internal.delete_object,
            Bucket=self._bucket,
            Key=key,
        )

    async def url_for(self, key: str, *, expires: timedelta = timedelta(minutes=5)) -> str:
        return await asyncio.to_thread(
            self._internal.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=int(expires.total_seconds()),
        )


class LocalDiskStorage:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    async def check(self) -> None:
        await asyncio.to_thread(self._root.mkdir, parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError("Storage key escapes the configured root")
        return path

    async def presign_put(self, key: str, *, expires: timedelta = timedelta(minutes=10)) -> str:
        raise RuntimeError("Browser uploads require S3-compatible storage; set S3_ENDPOINT in .env")

    async def stat(self, key: str) -> StoredObject | None:
        path = self._path(key)
        try:
            result = await asyncio.to_thread(path.stat)
        except FileNotFoundError:
            return None
        return StoredObject(size=result.st_size, etag=None)

    async def put(self, key: str, source: BinaryIO, *, size: int, content_type: str) -> None:
        del content_type
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)

        def write_file() -> None:
            with path.open("wb") as destination:
                while chunk := source.read(1024 * 1024):
                    destination.write(chunk)

        await asyncio.to_thread(write_file)
        if path.stat().st_size != size:
            await self.delete(key)
            raise ValueError("Uploaded byte count did not match the declared size")

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        try:
            await asyncio.to_thread(path.unlink)
        except FileNotFoundError:
            return

    async def url_for(self, key: str, *, expires: timedelta = timedelta(minutes=5)) -> str:
        raise NotImplementedError("Local files do not have signed browser URLs")


def get_storage(settings: Annotated[Settings, Depends(get_settings)]) -> StorageBackend:
    app_settings = settings
    return S3CompatibleStorage(
        internal_endpoint=app_settings.s3_endpoint,
        public_endpoint=app_settings.s3_public_endpoint,
        access_key=app_settings.s3_access_key,
        secret_key=app_settings.s3_secret_key,
        bucket=app_settings.s3_bucket,
    )