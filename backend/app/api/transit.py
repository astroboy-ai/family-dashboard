from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import Actor, get_current_actor
from app.services.transit import TransitOperator, build_transit_request, fetch_transit_eta


router = APIRouter(prefix="/transit", tags=["transit"])


@router.get("/eta")
async def get_transit_eta(
    _: Annotated[Actor, Depends(get_current_actor)],
    operator: TransitOperator,
    stop_id: str | None = Query(default=None, min_length=1, max_length=80),
    route: str | None = Query(default=None, min_length=1, max_length=20),
    service_type: int = Query(default=1, ge=1, le=2),
    company_id: Literal["ctb", "nwfb"] = "ctb",
    line: str | None = Query(default=None, min_length=2, max_length=4),
    station: str | None = Query(default=None, min_length=3, max_length=4),
    language: Literal["en", "tc"] = "en",
) -> dict:
    request = build_transit_request(
        operator=operator,
        stop_id=stop_id,
        route=route,
        service_type=service_type,
        company_id=company_id,
        line=line,
        station=station,
        language=language,
    )
    return {"operator": operator, "data": await fetch_transit_eta(request)}