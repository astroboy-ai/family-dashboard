from collections.abc import Awaitable, Callable

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from app.main import create_app


async def healthy_probe() -> None:
    return None


async def failing_probe() -> None:
    raise RuntimeError("private connection detail")


async def get_response(
    app: FastAPI,
    path: str,
) -> Response:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.get(path)


def make_app(
    probe: Callable[[], Awaitable[None]] = healthy_probe,
) -> FastAPI:
    probes = {"database": probe, "redis": healthy_probe, "storage": healthy_probe}
    return create_app(readiness_probes=probes)


async def test_healthz_is_live_without_dependency_checks() -> None:
    response = await get_response(make_app(failing_probe), "/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_returns_ok_when_all_probes_pass() -> None:
    response = await get_response(make_app(), "/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "redis": "ok", "storage": "ok"},
    }


async def test_readyz_hides_dependency_error_details() -> None:
    response = await get_response(make_app(failing_probe), "/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {
            "database": "unavailable",
            "redis": "ok",
            "storage": "ok",
        },
    }
    assert "private connection detail" not in response.text