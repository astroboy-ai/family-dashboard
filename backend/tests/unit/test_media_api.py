from collections.abc import AsyncIterator
from datetime import timedelta
import uuid

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import Actor, get_current_actor
from app.core.db import get_session
from app.core.storage import StoredObject, get_storage
from app.main import create_app
from app.models import JobOutbox, MediaAsset


class FakeResult:
    def __init__(self, value: object | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object | None:
        return self.value


class FakeSession:
    def __init__(self) -> None:
        self.asset: MediaAsset | None = None
        self.added: list[object] = []
        self.commit_count = 0

    async def execute(self, _: object) -> FakeResult:
        value = self.asset if self.commit_count else None
        return FakeResult(value)

    def add(self, value: object) -> None:
        self.added.append(value)
        if isinstance(value, MediaAsset):
            self.asset = value

    async def commit(self) -> None:
        self.commit_count += 1


class FakeStorage:
    async def presign_put(self, key: str, *, expires: timedelta) -> str:
        return f"https://storage.example.test/{key}?signature=test"

    async def stat(self, key: str) -> StoredObject:
        return StoredObject(size=1234, etag="test-etag")

    async def put(self, key: str, source: object, *, size: int, content_type: str) -> None:
        raise NotImplementedError

    async def get(self, key: str) -> bytes:
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        raise NotImplementedError

    async def url_for(self, key: str, *, expires: timedelta) -> str:
        raise NotImplementedError


async def unused_probe() -> None:
    return None


async def test_presign_to_complete_api_flow() -> None:
    actor = Actor(
        member_id=uuid.uuid4(),
        household_id=uuid.uuid4(),
        role="parent",
        display_name="Parent",
        timezone="Asia/Hong_Kong",
        locale="en",
    )
    session = FakeSession()
    storage = FakeStorage()
    app: FastAPI = create_app(readiness_probes={"database": unused_probe})

    async def fake_session() -> AsyncIterator[FakeSession]:
        yield session

    app.dependency_overrides[get_current_actor] = lambda: actor
    app.dependency_overrides[get_session] = fake_session
    app.dependency_overrides[get_storage] = lambda: storage

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        presign = await client.post(
            "/api/media/presign",
            json={
                "filename": "trip photo.jpg",
                "mime": "image/jpeg",
                "size": 1234,
                "sha256": "a" * 64,
            },
        )
        assert presign.status_code == 201, presign.text
        asset_id = presign.json()["asset_id"]
        complete = await client.post(f"/api/media/{asset_id}/complete")

    assert presign.status_code == 201
    assert presign.json()["upload_url"].startswith("https://storage.example.test/")
    assert presign.json()["deduplicated"] is False
    assert complete.status_code == 200
    assert complete.json() == {"asset_id": asset_id, "status": "pending", "queued": True, "already_complete": False}
    assert session.commit_count == 2
    assert sum(isinstance(item, JobOutbox) for item in session.added) == 1