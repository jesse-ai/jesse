from jesse.services.auth import require_auth
from typing import Optional
from fastapi import APIRouter, Header, Body, Depends
from fastapi.responses import JSONResponse

from jesse.services.multiprocessing import process_manager
from jesse.services.web import (
    LiveRequestJson, 
    LiveCancelRequestJson, 
    GetLogsRequestJson, 
    GetOrdersRequestJson,
    GetLiveSessionsRequestJson,
    UpdateLiveSessionNotesRequestJson,
    UpdateLiveSessionStateRequestJson
)
import jesse.helpers as jh
from jesse.repositories import live_session_repository
from jesse.services import transformers
from jesse_live import live_mode
from jesse_live.services.data_provider import get_logs as gl, get_orders as go
from jesse.enums import live_session_statuses, live_session_modes

router = APIRouter(prefix="/live", tags=["Live Trading"])


@router.post("")
def live(request_json: LiveRequestJson, authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)) -> JSONResponse:
    """
    Start live trading
    """

    jh.validate_cwd()

    trading_mode = live_session_modes.LIVETRADE if request_json.paper_mode is False else live_session_modes.PAPERTRADE

    live_session_repository.store_live_session(
        id=request_json.id,
        status=live_session_statuses.STARTING,
        session_mode=trading_mode,
        exchange=request_json.exchange,
        state={
            'form': {
                'debug_mode': request_json.debug_mode,
                'paper_mode': request_json.paper_mode,
                'exchange': request_json.exchange,
                'exchange_api_key_id': request_json.exchange_api_key_id,
                'notification_api_key_id': request_json.notification_api_key_id,
                'routes': request_json.routes,
                'data_routes': request_json.data_routes,
            }
        },
    )

    # execute live session
    process_manager.add_task(
        live_mode.run,
        request_json.id,
        request_json.debug_mode,
        request_json.exchange,
        request_json.exchange_api_key_id,
        request_json.notification_api_key_id,
        request_json.config,
        request_json.routes,
        request_json.data_routes,
        trading_mode,
    )

    mode = 'live' if request_json.paper_mode is False else 'paper'
    return JSONResponse({'message': f"Started {mode} trading..."}, status_code=202)


@router.post("/cancel")
def cancel_live(request_json: LiveCancelRequestJson, authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)):
    """
    Cancel live trading
    """

    process_manager.cancel_process(request_json.id)

    return JSONResponse({'message': f'Live process with ID of {request_json.id} terminated.'}, status_code=200)


@router.post('/logs')
def get_logs(json_request: GetLogsRequestJson, authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)) -> JSONResponse:
    """
    Get logs for a live trading session
    """

    arr = gl(json_request.id, json_request.type, json_request.start_time)

    return JSONResponse({
        'id': json_request.id,
        'data': arr
    }, status_code=200)


@router.post('/orders')
def get_orders(json_request: GetOrdersRequestJson, authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)) -> JSONResponse:
    """
    Get orders for a live trading session
    """

    arr = go(json_request.session_id)

    return JSONResponse({
        'id': json_request.id,
        'data': arr
    }, status_code=200)


@router.post("/sessions")
def get_live_sessions(
    request_json: GetLiveSessionsRequestJson = Body(default=GetLiveSessionsRequestJson()),
    authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)
):
    """
    Get a list of live sessions sorted by most recently updated with pagination
    """

    # Get sessions from the database with pagination and filters
    sessions = live_session_repository.get_live_sessions(
        limit=request_json.limit,
        offset=request_json.offset,
        title_search=request_json.title_search,
        status_filter=request_json.status_filter,
        date_filter=request_json.date_filter,
        mode_filter=request_json.mode_filter
    )

    # Transform the sessions using the transformer
    transformed_sessions = [transformers.get_live_session(session) for session in sessions]

    return JSONResponse({
        'sessions': transformed_sessions,
        'count': len(transformed_sessions)
    })


@router.post("/sessions/{session_id}")
def get_live_session_by_id(session_id: str, authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)):
    """
    Get a single live session by ID
    """

    # Get the session from the database
    session = live_session_repository.get_live_session_by_id(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    # Transform the session using the transformer
    transformed_session = transformers.get_live_session(session)

    return JSONResponse({
        'session': transformed_session
    })


@router.post("/sessions/{session_id}/remove")
def remove_live_session(session_id: str, authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)):
    """
    Remove a live session from the database
    """

    session = live_session_repository.get_live_session_by_id(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    # Delete the session from the database
    result = live_session_repository.delete_live_session(session_id)

    if not result:
        return JSONResponse({
            'error': f'Failed to delete session with ID {session_id}'
        }, status_code=500)

    return JSONResponse({
        'message': 'Live session removed successfully'
    })


@router.post("/sessions/{session_id}/notes")
def update_session_notes(
    session_id: str,
    request_json: UpdateLiveSessionNotesRequestJson,
    authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)
):
    """
    Update the notes (title, description, strategy_codes) of a live session
    """

    session = live_session_repository.get_live_session_by_id(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    live_session_repository.update_live_session_notes(
        session_id,
        request_json.title,
        request_json.description,
        request_json.strategy_codes
    )

    return JSONResponse({
        'message': 'Live session notes updated successfully'
    })


@router.post("/update-state")
def update_state(request_json: UpdateLiveSessionStateRequestJson, authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)):
    """
    Upsert live session state (creates draft if doesn't exist, updates if exists)
    """

    live_session_repository.upsert_live_session_state(request_json.id, request_json.state)

    return JSONResponse({
        'message': 'Live session state updated successfully'
    }, status_code=200)


@router.post("/purge-sessions")
def purge_sessions(request_json: dict = Body(...), authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)):
    """
    Purge live sessions older than specified days
    """

    days_old = request_json.get('days_old', None)

    deleted_count = live_session_repository.purge_live_sessions(days_old)

    return JSONResponse({
        'message': f'Successfully purged {deleted_count} session(s)',
        'deleted_count': deleted_count
    }, status_code=200)


@router.get("/equity-curve")
def get_equity_curve(
    session_id: str,
    from_ms: Optional[int] = None,
    to_ms: Optional[int] = None,
    timeframe: str = 'auto',
    max_points: int = 1000,
    authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)
) -> JSONResponse:
    """
    Get equity curve for a live session with downsampling
    """

    from jesse.repositories import live_equity_repository

    try:
        if from_ms is None:
            session = live_session_repository.get_live_session_by_id(session_id)
            if session and getattr(session, 'created_at', None):
                from_ms = session.created_at
            else:
                # fallback: last 24h
                from_ms = jh.now(True) - (24 * 60 * 60 * 1000)

        result = live_equity_repository.query_equity_curve(
            session_id=session_id,
            from_ms=from_ms,
            to_ms=to_ms,
            timeframe=timeframe,
            max_points=max_points
        )

        return JSONResponse(result, status_code=200)
    except Exception as e:
        return JSONResponse({
            'message': f'Error fetching equity curve: {str(e)}'
        }, status_code=500)
