from datetime import UTC, datetime, timedelta
from collections.abc import AsyncIterator
import uuid
from types import SimpleNamespace

import jwt
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient, Response
from pydantic import ValidationError

from app.api.auth import get_me
from app.api.deps import Actor, get_current_actor, require_role
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.main import create_app


def make_actor(role: str) -> Actor:
    return Actor(
        member_id=uuid.uuid4(),
        household_id=uuid.uuid4(),
        role=role,
        display_name="Test Member",
        timezone="Asia/Hong_Kong",
        locale="en",
        scopes=frozenset({"notes.read.own"}),
    )


async def get_response(app: FastAPI, path: str) -> Response:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.get(path)


class FakeResult:
    def __init__(self, row: tuple[object, object, object]) -> None:
        self.row = row

    def first(self) -> tuple[object, object, object]:
        return self.row


class FakeSession:
    def __init__(self, rows: list[tuple[object, object, object]]) -> None:
        self.rows = rows
        self.query_count = 0

    async def execute(self, _: object) -> FakeResult:
        row = self.rows[min(self.query_count, len(self.rows) - 1)]
        self.query_count += 1
        return FakeResult(row)

    async def commit(self) -> None:
        return None


async def unused_probe() -> None:
    return None


def test_password_hash_verifies_only_the_original_password() -> None:
    encoded = hash_password("correct horse battery staple")

    assert encoded != "correct horse battery staple"
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)


def test_production_settings_reject_development_jwt_secret() -> None:
    try:
        Settings(environment="production")
    except ValidationError:
        pass
    else:
        raise AssertionError("Production accepted the built-in development JWT secret")


def test_access_token_round_trips_identity_claims() -> None:
    settings = Settings(jwt_secret="test-only-secret-long-enough-for-hs256")
    member_id = str(uuid.uuid4())
    household_id = str(uuid.uuid4())
    issued_at = datetime.now(UTC) - timedelta(seconds=30)
    token = create_access_token(
        member_id=member_id,
        household_id=household_id,
        settings=settings,
        now=issued_at,
    )

    claims = decode_access_token(token, settings=settings, now=issued_at + timedelta(minutes=1))

    assert claims["sub"] == member_id
    assert claims["household_id"] == household_id
    assert claims["token_type"] == "access"


def test_access_token_rejects_expiration_and_wrong_token_type() -> None:
    settings = Settings(jwt_secret="test-only-secret-long-enough-for-hs256")
    issued_at = datetime.now(UTC) - timedelta(seconds=30)
    token = create_access_token(
        member_id=str(uuid.uuid4()),
        household_id=str(uuid.uuid4()),
        settings=settings,
        now=issued_at,
    )

    try:
        decode_access_token(token, settings=settings, now=issued_at + timedelta(minutes=16))
    except jwt.ExpiredSignatureError:
        pass
    else:
        raise AssertionError("Expired access token was accepted")

    wrong_type = jwt.encode(
        {"sub": str(uuid.uuid4()), "token_type": "refresh", "exp": issued_at + timedelta(minutes=5)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    try:
        decode_access_token(wrong_type, settings=settings, now=issued_at)
    except jwt.InvalidTokenError:
        pass
    else:
        raise AssertionError("Non-access token was accepted")


async def test_me_returns_actor_context() -> None:
    actor = make_actor("child")
    app = FastAPI()
    app.dependency_overrides[get_current_actor] = lambda: actor
    app.add_api_route("/me", get_me, methods=["GET"])

    response = await get_response(app, "/me")

    assert response.status_code == 200
    assert response.json() == {
        "member_id": str(actor.member_id),
        "household_id": str(actor.household_id),
        "display_name": "Test Member",
        "role": "child",
        "timezone": "Asia/Hong_Kong",
        "locale": "en",
        "scopes": ["notes.read.own"],
    }


async def test_child_is_denied_parent_only_route() -> None:
    actor = make_actor("child")
    app = FastAPI()
    app.dependency_overrides[get_current_actor] = lambda: actor

    @app.get("/parent-only")
    async def parent_only(
        _: Actor = Depends(require_role("parent")),
    ) -> dict[str, str]:
        return {"status": "ok"}

    response = await get_response(app, "/parent-only")

    assert response.status_code == 403
    assert response.json() == {"detail": "Permission denied"}


async def test_login_sets_cookie_and_me_resolves_member() -> None:
    settings = Settings(jwt_secret="test-only-secret-long-enough-for-hs256")
    user_id = uuid.uuid4()
    household_id = uuid.uuid4()
    member = SimpleNamespace(
        id=uuid.uuid4(),
        household_id=household_id,
        user_id=user_id,
        display_name="Test Parent",
        role="parent",
        permissions={},
        is_active=True,
    )
    user = SimpleNamespace(
        id=user_id,
        email="parent@example.test",
        password_hash=hash_password("correct password"),
        is_active=True,
        last_login_at=None,
    )
    household = SimpleNamespace(id=household_id, timezone="Asia/Hong_Kong", locale="en")
    session = FakeSession([(user, member, household), (member, user, household)])
    app = create_app(settings=settings, readiness_probes={"database": unused_probe})

    async def fake_session() -> AsyncIterator[FakeSession]:
        yield session

    app.dependency_overrides[get_session] = fake_session
    app.dependency_overrides[get_settings] = lambda: settings

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        login_response = await client.post(
            "/api/auth/login",
            json={"email": " PARENT@example.test ", "password": "correct password"},
        )
        me_response = await client.get("/api/auth/me")

    assert login_response.status_code == 200
    assert login_response.json() == {"member_id": str(member.id), "role": "parent"}
    assert login_response.cookies.get("access_token")
    assert "httponly" in login_response.headers["set-cookie"].lower()
    assert me_response.status_code == 200
    assert me_response.json()["member_id"] == str(member.id)
    assert me_response.json()["household_id"] == str(household_id)
    assert me_response.json()["role"] == "parent"


async def test_me_rejects_missing_access_cookie() -> None:
    app = create_app(readiness_probes={"database": unused_probe})
    response = await get_response(app, "/api/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


async def test_logout_clears_access_cookie() -> None:
    app = create_app(readiness_probes={"database": unused_probe})
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/auth/logout")

    assert response.status_code == 204
    assert 'access_token=""' in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]