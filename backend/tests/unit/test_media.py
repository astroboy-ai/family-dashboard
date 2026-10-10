from datetime import timedelta
from types import SimpleNamespace
import uuid

import pytest

from app.api.deps import Actor
from app.core.errors import AppError
from app.core.storage import StoredObject
from app.models import JobOutbox
from app.schemas.media import MediaPresignRequest
from app.services.media import complete_upload, create_upload


class FakeResult:
    def __init__(self, value: object | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object | None:
        return self.value


class FakeSession:
    def __init__(self, result_value: object | None = None) -> None:
        self.result_value = result_value
        self.added: list[object] = []
        self.commit_count = 0

    async def execute(self, _: object) -> FakeResult:
        return FakeResult(self.result_value)

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commit_count += 1


class FakeStorage:
    def __init__(self, stored_size: int | None = None) -> None:
        self.stored_size = stored_size
        self.presigned_keys: list[str] = []
        self.deleted_keys: list[str] = []

    async def presign_put(self, key: str, *, expires: timedelta) -> str:
        self.presigned_keys.append(key)
        return f"https://storage.example.test/{key}?signature=test"

    async def stat(self, key: str) -> StoredObject | None:
        if self.stored_size is None:
            return None
        return StoredObject(size=self.stored_size, etag="test-etag")

    async def put(self, key: str, source: object, *, size: int, content_type: str) -> None:
        raise NotImplementedError

    async def get(self, key: str) -> bytes:
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        self.deleted_keys.append(key)

    async def url_for(self, key: str, *, expires: timedelta) -> str:
        raise NotImplementedError


def make_actor() -> Actor:
    return Actor(
        member_id=uuid.uuid4(),
        household_id=uuid.uuid4(),
        role="parent",
        display_name="Parent",
        timezone="Asia/Hong_Kong",
        locale="en",
        scopes=frozenset({"notes.read"}),
    )


def make_payload() -> MediaPresignRequest:
    return MediaPresignRequest(
        filename="trip photo.jpg",
        mime="image/jpeg",
        size=1234,
        sha256="a" * 64,
    )


async def test_create_upload_presigns_and_persists_pending_asset() -> None:
    actor = make_actor()
    session = FakeSession()
    storage = FakeStorage()

    result = await create_upload(session=session, storage=storage, actor=actor, payload=make_payload())

    asset = session.added[0]
    assert result["upload_url"].startswith("https://storage.example.test/")
    assert result["deduplicated"] is False
    assert asset.household_id == actor.household_id
    assert asset.kind == "image"
    assert asset.size_bytes == 1234
    assert asset.sha256 == "a" * 64
    assert asset.enrichment_status == "uploading"
    assert session.commit_count == 1
    assert len(storage.presigned_keys) == 1
    assert str(actor.household_id) in storage.presigned_keys[0]


async def test_create_upload_deduplicates_within_household() -> None:
    existing = SimpleNamespace(id=uuid.uuid4())
    session = FakeSession(existing)
    storage = FakeStorage()

    result = await create_upload(
        session=session,
        storage=storage,
        actor=make_actor(),
        payload=make_payload(),
    )

    assert result["asset_id"] == existing.id
    assert result["deduplicated"] is True
    assert result["upload_url"] is None
    assert storage.presigned_keys == []
    assert session.commit_count == 0


async def test_complete_upload_verifies_size_and_enqueues_thumbnail_once() -> None:
    asset = SimpleNamespace(
        id=uuid.uuid4(),
        household_id=uuid.uuid4(),
        deleted_at=None,
        storage_key="household/media/original.jpg",
        size_bytes=1234,
        enrichment_status="uploading",
    )
    session = FakeSession(asset)
    storage = FakeStorage(stored_size=1234)

    result = await complete_upload(
        session=session,
        storage=storage,
        actor=Actor(
            member_id=uuid.uuid4(),
            household_id=asset.household_id,
            role="parent",
            display_name="Parent",
            timezone="UTC",
            locale="en",
        ),
        asset_id=asset.id,
    )

    assert result == {"asset_id": asset.id, "status": "pending", "queued": True}
    assert asset.enrichment_status == "pending"
    assert len(session.added) == 1
    assert isinstance(session.added[0], JobOutbox)
    assert session.added[0].topic == "media.thumbnail"
    assert session.added[0].payload == {"asset_id": str(asset.id)}
    assert session.commit_count == 1


async def test_complete_upload_rejects_wrong_size_and_removes_object() -> None:
    asset = SimpleNamespace(
        id=uuid.uuid4(),
        household_id=uuid.uuid4(),
        deleted_at=None,
        storage_key="household/media/original.jpg",
        size_bytes=1234,
        enrichment_status="uploading",
    )
    session = FakeSession(asset)
    storage = FakeStorage(stored_size=10)
    actor = Actor(
        member_id=uuid.uuid4(),
        household_id=asset.household_id,
        role="parent",
        display_name="Parent",
        timezone="UTC",
        locale="en",
    )

    with pytest.raises(AppError) as error:
        await complete_upload(
            session=session,
            storage=storage,
            actor=actor,
            asset_id=asset.id,
        )

    assert error.value.error_code == "upload_size_mismatch"
    assert storage.deleted_keys == [asset.storage_key]
    assert session.commit_count == 0


async def test_complete_upload_is_idempotent_after_enqueue() -> None:
    asset = SimpleNamespace(
        id=uuid.uuid4(),
        household_id=uuid.uuid4(),
        deleted_at=None,
        storage_key="household/media/original.jpg",
        size_bytes=1234,
        enrichment_status="pending",
    )
    session = FakeSession(asset)
    storage = FakeStorage(stored_size=1234)
    actor = Actor(
        member_id=uuid.uuid4(),
        household_id=asset.household_id,
        role="parent",
        display_name="Parent",
        timezone="UTC",
        locale="en",
    )

    result = await complete_upload(
        session=session,
        storage=storage,
        actor=actor,
        asset_id=asset.id,
    )

    assert result["already_complete"] is True
    assert session.added == []
    assert session.commit_count == 0