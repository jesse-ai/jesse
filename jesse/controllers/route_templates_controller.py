import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from jesse.info import exchange_info
from jesse.repositories import route_template_repository
from jesse.services.auth import require_auth


router = APIRouter(dependencies=[Depends(require_auth)])
TemplateName = Annotated[str, Field(min_length=1, max_length=80)]
RouteValue = Annotated[str, Field(min_length=1, max_length=255)]


class TradingRouteTemplateItem(BaseModel):
    exchange: RouteValue
    symbol: RouteValue
    timeframe: RouteValue
    strategy: RouteValue


class DataRouteTemplateItem(BaseModel):
    exchange: RouteValue
    symbol: RouteValue
    timeframe: RouteValue


class RouteTemplatePayload(BaseModel):
    name: TemplateName
    routes: Annotated[list[TradingRouteTemplateItem], Field(min_length=1, max_length=50)]
    data_routes: Annotated[list[DataRouteTemplateItem], Field(max_length=50)]


class RouteTemplateUpdateRequest(RouteTemplatePayload):
    id: UUID


class RouteTemplateIdRequest(BaseModel):
    id: UUID


class RouteTemplateResponse(BaseModel):
    id: UUID
    name: str
    routes: list[TradingRouteTemplateItem]
    data_routes: list[DataRouteTemplateItem]
    created_at: int
    updated_at: int
    last_used_at: int


class RouteTemplatesResponse(BaseModel):
    templates: list[RouteTemplateResponse]


def _normalized_payload(
    request: RouteTemplatePayload,
) -> tuple[str, list[dict[str, str]], list[dict[str, str]]]:
    name = request.name.strip()
    routes = [
        {key: value.strip() for key, value in route.model_dump().items()}
        for route in request.routes
    ]
    data_routes = [
        {key: value.strip() for key, value in route.model_dump().items()}
        for route in request.data_routes
    ]

    if not name:
        raise HTTPException(status_code=422, detail='Route setup name is required')

    route_keys: set[tuple[str, str]] = set()
    quote_assets: set[str] = set()
    for route in routes:
        if not all(route.values()):
            raise HTTPException(status_code=422, detail='All trading route fields are required')
        if route['exchange'] not in exchange_info:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown exchange: {route['exchange']}",
            )
        if route['timeframe'] not in exchange_info[route['exchange']]['supported_timeframes']:
            raise HTTPException(
                status_code=422,
                detail=f"{route['timeframe']} is not supported by {route['exchange']}",
            )
        strategy_path = os.path.join(os.getcwd(), 'strategies', route['strategy'])
        if (
            os.path.basename(route['strategy']) != route['strategy']
            or not os.path.isdir(strategy_path)
        ):
            raise HTTPException(
                status_code=422,
                detail=f"Unknown strategy: {route['strategy']}",
            )
        if '-' not in route['symbol']:
            raise HTTPException(status_code=422, detail='Trading route symbols must contain "-"')
        key = (route['exchange'], route['symbol'])
        if key in route_keys:
            raise HTTPException(
                status_code=422,
                detail='Each exchange-symbol pair can be traded only once',
            )
        route_keys.add(key)
        quote_assets.add(route['symbol'].rsplit('-', 1)[1])

    if len(quote_assets) > 1:
        raise HTTPException(
            status_code=422,
            detail='All trading routes must use the same quote asset',
        )

    data_keys: set[tuple[str, str, str]] = set()
    trading_candles = {
        (route['exchange'], route['symbol'], route['timeframe'])
        for route in routes
    }
    for route in data_routes:
        if not all(route.values()):
            raise HTTPException(status_code=422, detail='All data route fields are required')
        if route['exchange'] not in exchange_info:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown exchange: {route['exchange']}",
            )
        if route['timeframe'] not in exchange_info[route['exchange']]['supported_timeframes']:
            raise HTTPException(
                status_code=422,
                detail=f"{route['timeframe']} is not supported by {route['exchange']}",
            )
        if '-' not in route['symbol']:
            raise HTTPException(status_code=422, detail='Data route symbols must contain "-"')
        key = (route['exchange'], route['symbol'], route['timeframe'])
        if key in data_keys:
            raise HTTPException(
                status_code=422,
                detail='Duplicate data routes are not allowed',
            )
        if key in trading_candles:
            raise HTTPException(
                status_code=422,
                detail='A data route cannot duplicate a trading route candle',
            )
        data_keys.add(key)

    return name, routes, data_routes


def _translate_repository_error(exc: Exception) -> None:
    if isinstance(exc, route_template_repository.RouteTemplateConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, route_template_repository.RouteTemplateNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    raise exc


@router.post('/route-templates/list', response_model=RouteTemplatesResponse)
async def list_route_templates():
    return RouteTemplatesResponse(
        templates=route_template_repository.get_route_templates()
    )


@router.post('/route-templates/add', response_model=RouteTemplatesResponse)
async def add_route_template(request: RouteTemplatePayload):
    name, routes, data_routes = _normalized_payload(request)
    try:
        templates = route_template_repository.add_route_template(
            name, routes, data_routes
        )
    except Exception as exc:
        _translate_repository_error(exc)
        raise
    return RouteTemplatesResponse(templates=templates)


@router.post('/route-templates/update', response_model=RouteTemplatesResponse)
async def update_route_template(request: RouteTemplateUpdateRequest):
    name, routes, data_routes = _normalized_payload(request)
    try:
        templates = route_template_repository.update_route_template(
            request.id, name, routes, data_routes
        )
    except Exception as exc:
        _translate_repository_error(exc)
        raise
    return RouteTemplatesResponse(templates=templates)


@router.post('/route-templates/remove', response_model=RouteTemplatesResponse)
async def remove_route_template(request: RouteTemplateIdRequest):
    try:
        templates = route_template_repository.remove_route_template(request.id)
    except Exception as exc:
        _translate_repository_error(exc)
        raise
    return RouteTemplatesResponse(templates=templates)


@router.post('/route-templates/touch', response_model=RouteTemplatesResponse)
async def touch_route_template(request: RouteTemplateIdRequest):
    try:
        templates = route_template_repository.touch_route_template(request.id)
    except Exception as exc:
        _translate_repository_error(exc)
        raise
    return RouteTemplatesResponse(templates=templates)
