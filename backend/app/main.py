import asyncio
from collections.abc import Awaitable, Callable, Mapping
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.internal_agent import router as internal_agent_router
from app.api.graph import router as graph_router
from app.api.graph_views import router as graph_views_router
from app.api.media import router as media_router
from app.api.notes import blocks_router, notes_router, tag_proposals_router, tags_router
from app.api.search import router as search_router
from app.api.transit import router as transit_router
from app.core.config import Settings, get_settings
from app.core.db import check_database, dispose_database
from app.core.errors import AppError, app_error_handler
from app.core.logging import configure_logging
from app.core.storage import get_storage


ReadinessProbe = Callable[[], Awaitable[None]]
logger = structlog.get_logger(__name__)


def create_app(
    *,
    settings: Settings | None = None,
    readiness_probes: Mapping[str, ReadinessProbe] | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        configure_logging(app_settings.log_level)
        try:
            yield
        finally:
            await dispose_database()

    async def check_redis() -> None:
        client = Redis.from_url(
            app_settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        try:
            await client.ping()
        finally:
            await client.aclose()

    async def check_storage() -> None:
        await get_storage(app_settings).check()

    probes = readiness_probes or {
        "database": check_database,
        "redis": check_redis,
        "storage": check_storage,
    }
    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(auth_router, prefix="/api")
    app.include_router(media_router, prefix="/api")
    app.include_router(notes_router, prefix="/api")
    app.include_router(blocks_router, prefix="/api")
    app.include_router(tags_router, prefix="/api")
    app.include_router(tag_proposals_router, prefix="/api")
    app.include_router(search_router, prefix="/api")
    app.include_router(internal_agent_router)
    app.include_router(graph_router, prefix="/api")
    app.include_router(graph_views_router, prefix="/api")
    app.include_router(transit_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        async def run_probe(name: str, probe: ReadinessProbe) -> tuple[str, str]:
            try:
                await probe()
            except Exception as error:
                logger.warning(
                    "readiness_check_failed",
                    check=name,
                    error_type=type(error).__name__,
                )
                return name, "unavailable"
            return name, "ok"

        results = await asyncio.gather(
            *(run_probe(name, probe) for name, probe in probes.items())
        )
        checks = dict(results)
        is_ready = all(status == "ok" for status in checks.values())
        return JSONResponse(
            status_code=200 if is_ready else 503,
            content={"status": "ok" if is_ready else "not_ready", "checks": checks},
        )

    return app


app = create_app()