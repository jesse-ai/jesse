import traceback
from typing import Callable

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

import jesse.helpers as jh
from jesse.controllers.project_files_controller import respond
from jesse.services import session_results
from jesse.services.auth import require_auth
from jesse.services.web import LiveSessionsListRequestJson, SessionResultsRequestJson

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
             'message': f'Jesse could not read this session ({type(e).__name__}). Check the Jesse log for details.'},
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
