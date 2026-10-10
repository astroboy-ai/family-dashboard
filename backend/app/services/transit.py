import asyncio
import time
from dataclasses import dataclass
from urllib.parse import quote
from typing import Literal

import httpx

from app.core.errors import AppError


TransitOperator = Literal["kmb", "ctb", "gmb", "mtr"]


@dataclass(frozen=True)
class TransitRequest:
    url: str
    params: dict[str, str]


_CACHE_TTL_SECONDS = 20
_CACHE_MAX_ENTRIES = 256
_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = asyncio.Lock()


def build_transit_request(
    *,
    operator: TransitOperator,
    stop_id: str | None = None,
    route: str | None = None,
    service_type: int = 1,
    company_id: Literal["ctb", "nwfb"] = "ctb",
    line: str | None = None,
    station: str | None = None,
    language: Literal["en", "tc"] = "en",
) -> TransitRequest:
    if operator == "kmb":
        if not stop_id or not route:
            raise AppError("KMB ETA requires a stop ID and route", error_code="invalid_transit_query")
        return TransitRequest(
            url=f"https://data.etabus.gov.hk/v1/transport/kmb/eta/{quote(stop_id, safe='')}/{quote(route, safe='')}/{service_type}",
            params={"lang": language},
        )
    if operator == "ctb":
        if not stop_id or not route:
            raise AppError("Citybus ETA requires a stop ID and route", error_code="invalid_transit_query")
        return TransitRequest(
            url=f"https://rt.data.gov.hk/v1.2/transport/citybus/eta/{company_id}/{quote(stop_id, safe='')}/{quote(route, safe='')}",
            params={"lang": language},
        )
    if operator == "gmb":
        if not stop_id:
            raise AppError("GMB ETA requires a stop ID", error_code="invalid_transit_query")
        return TransitRequest(
            url=f"https://data.etagmb.gov.hk/eta/stop/{quote(stop_id, safe='')}",
            params={"lang": language},
        )
    if not line or not station:
        raise AppError("MTR ETA requires a line and station", error_code="invalid_transit_query")
    return TransitRequest(
        url="https://rt.data.gov.hk/v1/transport/mtr/getSchedule.php",
        params={"line": line, "sta": station, "lang": language},
    )


async def fetch_transit_eta(request: TransitRequest) -> dict:
    cache_key = f"{request.url}?{sorted(request.params.items())}"
    now = time.monotonic()
    async with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(request.url, params=request.params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise AppError(
            "Transit provider is temporarily unavailable",
            status_code=502,
            error_code="transit_provider_unavailable",
        ) from error

    async with _cache_lock:
        if len(_cache) >= _CACHE_MAX_ENTRIES:
            expired_keys = [key for key, (expires_at, _) in _cache.items() if expires_at <= now]
            for key in expired_keys:
                _cache.pop(key, None)
            if len(_cache) >= _CACHE_MAX_ENTRIES:
                _cache.pop(next(iter(_cache)))
        _cache[cache_key] = (now + _CACHE_TTL_SECONDS, payload)
    return payload