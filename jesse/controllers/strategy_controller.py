from typing import Optional
from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from jesse.services import auth as authenticator
from jesse.services.web import (
    NewStrategyRequestJson,
    GetStrategyRequestJson,
    SaveStrategyRequestJson,
    DeleteStrategyRequestJson
)
import jesse.helpers as jh

router = APIRouter(prefix="/strategy", tags=["Strategy"])


@router.post("/make")
def make_strategy(json_request: NewStrategyRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Create a new strategy
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import strategy_handler
    return strategy_handler.generate(json_request.name)


@router.get("/all")
def get_strategies(authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Get all strategies
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import strategy_handler
    return strategy_handler.get_strategies()


@router.post("/get")
def get_strategy(
        json_request: GetStrategyRequestJson,
        authorization: Optional[str] = Header(None)
) -> JSONResponse:
    """
    Get a specific strategy
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import strategy_handler
    return strategy_handler.get_strategy(json_request.name)


@router.post("/save")
def save_strategy(
        json_request: SaveStrategyRequestJson,
        authorization: Optional[str] = Header(None)
) -> JSONResponse:
    """
    Save a strategy
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import strategy_handler
    return strategy_handler.save_strategy(json_request.name, json_request.content)


@router.post("/delete")
def delete_strategy(
        json_request: DeleteStrategyRequestJson,
        authorization: Optional[str] = Header(None)
) -> JSONResponse:
    """
    Delete a strategy
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import strategy_handler
    return strategy_handler.delete_strategy(json_request.name)
