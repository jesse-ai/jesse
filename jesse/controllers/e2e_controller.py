"""Authenticated E2E endpoints for inspecting, resetting, and seeding test data."""

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from jesse.services.auth import require_auth
from jesse.services.db import postgres_schema
from jesse.services.env import is_test_env
from jesse.services.e2e_database import inspect_test_candles, reset_test_data, seed_test_data


# Every endpoint uses the /testing prefix and requires normal dashboard authentication.
router = APIRouter(
    prefix='/testing',
    tags=['Testing'],
    dependencies=[Depends(require_auth)],
)


class InspectCandlesRequest(BaseModel):
    """Identify the stored market whose real candle rows should be inspected."""

    exchange: str
    symbol: str


@router.get('/status')
def status() -> JSONResponse:
    """Report whether test mode is active and which PostgreSQL schema is in use."""
    return JSONResponse({
        'is_test_env': is_test_env(),
        'postgres_schema': postgres_schema(),
    })


@router.post('/reset')
def reset() -> JSONResponse:
    """Clear all tables in the configured test schema and report how many were reset."""
    return JSONResponse({
        'tables_reset': reset_test_data(),
    })


@router.post('/seed')
def seed(payload: dict = Body(...)) -> JSONResponse:
    """Insert the backtest sessions and candles supplied by an E2E test."""
    return JSONResponse(seed_test_data(payload))


@router.post('/candles/inspect')
def inspect_candles(request: InspectCandlesRequest) -> JSONResponse:
    """Return integrity metrics calculated from rows in the guarded test schema."""
    return JSONResponse(inspect_test_candles(request.exchange, request.symbol))
