import asyncio
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Annotated, BinaryIO, Protocol
from urllib.parse import urlsplit

from fastapi import Depends
from minio import Minio
from minio.error import S3Error

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class StoredObject:
    size: int
    etag: str | None


class StorageBackend(Protocol):
    async def presign_put(self, key: str, *, expires: timedelta) -> str: ...

    async def stat(self, key: str) -> StoredObject | None: ...

    async def put(self, key: str, source: BinaryIO, *, size: int, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...

    async def url_for(self, key: str, *, expires: timedelta) -> str: ...


def _minio_client(endpoint: str, access_key: str, secret_key: str) -> Minio:
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("S3 endpoint must be an absolute HTTP or HTTPS URL")
    return Minio(
        parsed.netloc,
        access_key=access_key,
        secret_key=secret_key,
        region="us-east-1",
        secure=parsed.scheme == "https",
    )


class MinioStorage:
    def __init__(
        self,
        *,
        internal_endpoint: str,
        public_endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
    ) -> None:
        self._internal = _minio_client(internal_endpoint, access_key, secret_key)
        self._public = _minio_client(public_endpoint, access_key, secret_key)
        self._bucket = bucket

    async def presign_put(self, key: str, *, expires: timedelta = timedelta(minutes=10)) -> str:
        return await asyncio.to_thread(
            self._public.presigned_put_object,
            self._bucket,
            key,
            expires=expires,
        )

    async def stat(self, key: str) -> StoredObject | None:
        try:
            result = await asyncio.to_thread(self._internal.stat_object, self._bucket, key)
        except S3Error as error:
            if error.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                return None
            raise
        return StoredObject(size=result.size, etag=result.etag)

    async def put(self, key: str, source: BinaryIO, *, size: int, content_type: str) -> None:
        await asyncio.to_thread(
            self._internal.put_object,
            self._bucket,
            key,
            source,
            size,
            content_type=content_type,
        )

    async def get(self, key: str) -> bytes:
        response = await asyncio.to_thread(self._internal.get_object, self._bucket, key)
        try:
            return await asyncio.to_thread(response.read)
        finally:
            await asyncio.to_thread(response.close)
            await asyncio.to_thread(response.release_conn)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._internal.remove_object, self._bucket, key)

    async def url_for(self, key: str, *, expires: timedelta = timedelta(minutes=5)) -> str:
        return await asyncio.to_thread(
            self._internal.presigned_get_object,
            self._bucket,
            key,
            expires=expires,
        )


class LocalDiskStorage:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError("Storage key escapes the configured root")
        return path

    async def presign_put(self, key: str, *, expires: timedelta = timedelta(minutes=10)) -> str:
        raise NotImplementedError("Browser uploads require a network-addressable S3-compatible backend")

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
    return MinioStorage(
        internal_endpoint=app_settings.s3_endpoint,
        public_endpoint=app_settings.s3_public_endpoint,
        access_key=app_settings.s3_access_key,
        secret_key=app_settings.s3_secret_key,
        bucket=app_settings.s3_bucket,
    )