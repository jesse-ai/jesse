import traceback
from typing import Callable

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

import jesse.helpers as jh
from jesse.controllers.project_files_controller import respond
from jesse.services import live_history, session_results
from jesse.services.auth import require_auth
from jesse.services.web import (
    LiveHistoryRequestJson,
    LiveOrdersHistoryRequestJson,
    LiveSessionsListRequestJson,
    SessionResultsRequestJson,
)

# Bounded, read-only views of stored session results for MCP assistants. Live/paper sessions
# additionally require the live trading plugin; see jesse.services.session_results.
router = APIRouter(prefix="/session-results", tags=["Session Results"], dependencies=[Depends(require_auth)])


def respond_reading(operation: Callable[..., dict], *args) -> JSONResponse:
    """
    Like `respond`, but a failure while reading stored data (for example the database being
    unavailable) becomes a stable `read_failed` error naming only the exception type; the
    details go to the Jesse log, since stored text could contain anything.
    """
    try:
        return respond(operation, *args)
    except Exception as e:
        jh.debug(f'Reading session results failed: {traceback.format_exc()}')
        return JSONResponse(
            {'status': 'error', 'error_type': 'read_failed',
             'message': f'Jesse could not read the stored data ({type(e).__name__}). Check the Jesse log for details.'},
            status_code=500,
        )


@router.post("/get")
def get_session_results(json_request: SessionResultsRequestJson) -> JSONResponse:
    return respond_reading(
        session_results.get_results,
        json_request.session_type, json_request.session_id, json_request.section,
        json_request.offset, json_request.limit,
    )


@router.post("/live-sessions")
def list_live_sessions(json_request: LiveSessionsListRequestJson) -> JSONResponse:
    return respond_reading(
        session_results.list_live_sessions,
        json_request.limit, json_request.offset, json_request.status_filter,
        json_request.mode_filter, json_request.title_search,
    )


def _checked(operation: Callable[..., dict], dataset: str, json_request) -> Callable[..., dict]:
    """`operation`, refusing any request field the history route does not know (see live_history)."""
    def run(*args) -> dict:
        live_history.refuse_unknown_fields(dataset, json_request.model_extra)
        return operation(*args)
    return run


@router.post("/live-trades")
def list_live_trades(json_request: LiveHistoryRequestJson) -> JSONResponse:
    """Closed trades across live/paper sessions in a date window (Jesse's records, not the exchange's)."""
    return respond_reading(
        _checked(live_history.list_trades, 'live_trades', json_request),
        json_request.start, json_request.end, json_request.recent_days, json_request.mode, json_request.exchange,
        json_request.symbol, json_request.session_id, json_request.order, json_request.cursor, json_request.limit,
    )


@router.post("/live-orders")
def list_live_orders(json_request: LiveOrdersHistoryRequestJson) -> JSONResponse:
    """Orders across live/paper sessions in a date window (Jesse's records, not the exchange's)."""
    return respond_reading(
        _checked(live_history.list_orders, 'live_orders', json_request),
        json_request.start, json_request.end, json_request.recent_days, json_request.mode, json_request.exchange,
        json_request.symbol, json_request.session_id, json_request.time_field, json_request.status,
        json_request.order, json_request.cursor, json_request.limit,
    )
