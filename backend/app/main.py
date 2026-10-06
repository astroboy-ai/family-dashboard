import asyncio
import contextlib
import socket
from collections.abc import Awaitable, Callable, Mapping
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.routing import Mount

from mcp.server.transport_security import TransportSecuritySettings

from app.agent.mcp_server import (
    MCP_INTERNAL_HOSTNAME,
    MCP_MOUNT_PATH,
    MCP_PUBLIC_BASE_URL,
    MCP_PUBLIC_HOSTNAME,
    mcp_lifespan,
    mcp_server,
)
from app.api.admin import router as admin_router
from app.api.agent_tokens import router as agent_tokens_router
from app.api.notifications import router as notifications_router
from app.api.vault import router as vault_router
from app.api.auth import router as auth_router
from app.api.calendar import router as calendar_router
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


def _local_ipv4_addresses() -> set[str]:
    """Every IPv4 address this container answers on.

    Needed for the MCP transport's allowed-hosts list: co-located agents may
    connect by service name *or* by the container's address, and the SDK matches
    the host exactly (only the port may be wildcarded). Resolved at startup so
    the list follows the container rather than hard-coding a subnet.
    """

    addresses: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(str(info[4][0]))
    except OSError:
        pass
    # A UDP connect() to a routable address reports the interface address without
    # sending a packet — a fallback for when the hostname does not resolve.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("172.18.0.1", 1))
            addresses.add(probe.getsockname()[0])
    except OSError:
        pass
    return {address for address in addresses if address and not address.startswith("127.")}


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
            # The MCP session manager must be running for the mounted MCP app to
            # serve requests; without it every call returns 500.
            async with contextlib.AsyncExitStack() as stack:
                await stack.enter_async_context(mcp_lifespan())
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
    app.include_router(agent_tokens_router, prefix="/api")
    app.include_router(notifications_router, prefix="/api")
    app.include_router(vault_router, prefix="/api")
    app.include_router(calendar_router, prefix="/api")

    # MCP for agents (Hermes, Kururu). Mounted with the endpoint at the mount
    # point itself, so clients connect to /mcp rather than /mcp/mcp.
    #
    # The transport security settings are passed explicitly. Left to itself the
    # SDK sees the default ``host="127.0.0.1"`` and turns on DNS-rebinding
    # protection with only loopback hostnames allowed, so every request through
    # the tunnel is rejected with 421 Invalid Host header. Passing ``host``
    # suppresses that default, and the explicit settings below keep the
    # protection on with our own hostnames allowed instead of switching it off.
    app.router.routes.append(
        Mount(
            MCP_MOUNT_PATH,
            app=mcp_server.streamable_http_app(
                streamable_http_path="/",
                stateless_http=False,
                json_response=True,
                host=MCP_PUBLIC_HOSTNAME,
                transport_security=TransportSecuritySettings(
                    enable_dns_rebinding_protection=True,
                    allowed_hosts=[
                        # External agents arrive through the tunnel.
                        MCP_PUBLIC_HOSTNAME,
                        f"{MCP_PUBLIC_HOSTNAME}:*",
                        # Co-located agents arrive over the compose service name.
                        # Without this the tunnel works and every internal caller
                        # gets 421 Invalid Host header.
                        MCP_INTERNAL_HOSTNAME,
                        f"{MCP_INTERNAL_HOSTNAME}:*",
                        # …or by the container's own address. Resolved at startup
                        # because the SDK matches the host exactly: only the port
                        # may be wildcarded, so "172.18.0.*" would be read as a
                        # literal and match nothing.
                        *[f"{ip}:*" for ip in _local_ipv4_addresses()],
                        "localhost:*",
                        "127.0.0.1:*",
                    ],
                    allowed_origins=[
                        MCP_PUBLIC_BASE_URL,
                        f"http://{MCP_INTERNAL_HOSTNAME}:*",
                        "http://localhost:*",
                        "http://127.0.0.1:*",
                    ],
                ),
            ),
        )
    )

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