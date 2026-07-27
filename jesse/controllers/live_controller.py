from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from jesse.services.auth import require_auth, require_auth_token
from jesse.services.multiprocessing import process_manager
from jesse.services.web import (
    LiveRequestJson,
    LiveCancelRequestJson,
    GetLogsRequestJson,
    GetStrategyChartsRequestJson,
    GetLiveSessionChartDataRequestJson,
    GetOrdersRequestJson,
    GetLiveSessionsRequestJson,
    UpdateLiveSessionNotesRequestJson,
    UpdateLiveSessionStateRequestJson
)
import jesse.helpers as jh
from jesse.repositories import live_session_repository
from jesse.services import transformers
from jesse.modes.data_provider import download_live_log
from jesse.enums import live_session_statuses, live_session_modes

router = APIRouter(prefix="/live", tags=["Live Trading"])


@router.post("", dependencies=[Depends(require_auth)])
def live(request_json: LiveRequestJson) -> JSONResponse:
    """
    Start live trading
    """
    from jesse_live import live_mode

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


@router.post("/cancel", dependencies=[Depends(require_auth)])
def cancel_live(request_json: LiveCancelRequestJson):
    """
    Cancel live trading
    """

    process_manager.cancel_process(request_json.id)

    return JSONResponse({'message': f'Live process with ID of {request_json.id} terminated.'}, status_code=200)


@router.post('/logs', dependencies=[Depends(require_auth)])
def get_logs(json_request: GetLogsRequestJson) -> JSONResponse:
    """
    Get logs for a live trading session
    """
    from jesse_live.services.data_provider import get_logs

    arr = get_logs(json_request.id, json_request.type, json_request.start_time)

    return JSONResponse({
        'id': json_request.id,
        'data': arr
    }, status_code=200)


@router.post('/strategy-charts', dependencies=[Depends(require_auth)])
def get_strategy_charts(json_request: GetStrategyChartsRequestJson) -> JSONResponse:
    """
    Get the strategy-drawn chart data (indicator lines, extra charts,
    horizontal lines) of a running live session, keyed by route key.
    The live process keeps a snapshot in redis; this hydrates the dashboard
    chart after a page (re)load.
    """

    from jesse.services.redis import get_live_charts_snapshot

    return JSONResponse({
        'id': json_request.id,
        'data': get_live_charts_snapshot(json_request.id)
    }, status_code=200)


@router.post('/orders', dependencies=[Depends(require_auth)])
def get_orders(json_request: GetOrdersRequestJson) -> JSONResponse:
    """
    Get orders for a live trading session
    """
    from jesse_live.services.data_provider import get_orders

    arr = get_orders(json_request.session_id)

    return JSONResponse({
        'id': json_request.id,
        'data': arr
    }, status_code=200)


@router.post("/sessions", dependencies=[Depends(require_auth)])
def get_live_sessions(
    request_json: GetLiveSessionsRequestJson = Body(default=GetLiveSessionsRequestJson()),
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


@router.post("/sessions/{session_id}", dependencies=[Depends(require_auth)])
def get_live_session_by_id(session_id: UUID):
    """
    Get a single live session by ID
    """

    # Get the session from the database
    session = live_session_repository.get_live_session_by_id(str(session_id))

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    # Transform the session using the transformer
    transformed_session = transformers.get_live_session(session)

    return JSONResponse({
        'session': transformed_session
    })


@router.post("/sessions/{session_id}/chart-data", dependencies=[Depends(require_auth)])
def get_live_session_chart_data(
    session_id: UUID,
    request_json: GetLiveSessionChartDataRequestJson,
):
    session = live_session_repository.get_live_session_by_id(str(session_id))

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    try:
        from jesse.services.live_chart_service import get_live_session_chart_data as build_chart_data

        return JSONResponse({
            'chart_data': build_chart_data(
                session,
                request_json.exchange,
                request_json.symbol,
                request_json.timeframe,
                request_json.anchor_time,
                request_json.candle_count,
            )
        })
    except ValueError as e:
        return JSONResponse({'error': str(e)}, status_code=400)


@router.post("/sessions/{session_id}/remove", dependencies=[Depends(require_auth)])
def remove_live_session(session_id: UUID):
    """
    Remove a live session from the database
    """

    session = live_session_repository.get_live_session_by_id(str(session_id))

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    # Delete the session from the database
    result = live_session_repository.delete_live_session(str(session_id))

    if not result:
        return JSONResponse({
            'error': f'Failed to delete session with ID {session_id}'
        }, status_code=500)

    return JSONResponse({
        'message': 'Live session removed successfully'
    })


@router.post("/sessions/{session_id}/notes", dependencies=[Depends(require_auth)])
def update_session_notes(
    session_id: UUID,
    request_json: UpdateLiveSessionNotesRequestJson,
):
    """
    Update the notes (title, description, strategy_codes) of a live session
    """

    session = live_session_repository.get_live_session_by_id(str(session_id))

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    live_session_repository.update_live_session_notes(
        str(session_id),
        request_json.title,
        request_json.description,
        request_json.strategy_codes
    )

    return JSONResponse({
        'message': 'Live session notes updated successfully'
    })


@router.post("/update-state", dependencies=[Depends(require_auth)])
def update_state(request_json: UpdateLiveSessionStateRequestJson):
    """
    Upsert live session state (creates draft if doesn't exist, updates if exists)
    """

    live_session_repository.upsert_live_session_state(request_json.id, request_json.state)

    return JSONResponse({
        'message': 'Live session state updated successfully'
    }, status_code=200)


@router.post("/purge-sessions", dependencies=[Depends(require_auth)])
def purge_sessions(request_json: dict = Body(...)):
    """
    Purge live sessions older than specified days
    """

    days_old = request_json.get('days_old', None)

    deleted_count = live_session_repository.purge_live_sessions(days_old)

    return JSONResponse({
        'message': f'Successfully purged {deleted_count} session(s)',
        'deleted_count': deleted_count
    }, status_code=200)


@router.get("/download-log/{session_id}", dependencies=[Depends(require_auth_token)])
def download_live_log_handler(session_id: UUID):
    """
    Download log file for a specific live session
    """

    try:
        return download_live_log(str(session_id))
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.get("/equity-curve", dependencies=[Depends(require_auth)])
def get_equity_curve(
    session_id: str,
    from_ms: Optional[int] = None,
    to_ms: Optional[int] = None,
    timeframe: str = 'auto',
    max_points: int = 1000,
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
