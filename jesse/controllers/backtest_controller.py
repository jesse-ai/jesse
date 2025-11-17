from typing import Optional
from fastapi import APIRouter, Header, Query, Body
from fastapi.responses import JSONResponse, FileResponse
import json
from jesse.services import auth as authenticator
from jesse.services.multiprocessing import process_manager
from jesse.services.web import BacktestRequestJson, CancelRequestJson, UpdateBacktestSessionStateRequestJson, GetBacktestSessionsRequestJson, UpdateBacktestSessionNotesRequestJson
import jesse.helpers as jh
from jesse.models.BacktestSession import (
    get_backtest_sessions as get_sessions,
    update_backtest_session_state,
    update_backtest_session_notes,
    delete_backtest_session,
    get_backtest_session_by_id as get_backtest_session_by_id_from_db
)
from jesse.services.transformers import get_backtest_session, get_backtest_session_for_load_more

router = APIRouter(prefix="/backtest", tags=["Backtest"])


@router.post("")
def backtest(request_json: BacktestRequestJson, authorization: Optional[str] = Header(None)):
    """
    Start a backtest process
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    jh.validate_cwd()

    from jesse.modes.backtest_mode import run as run_backtest

    process_manager.add_task(
        run_backtest,
        request_json.id,
        request_json.debug_mode,
        request_json.config,
        request_json.exchange,
        request_json.routes,
        request_json.data_routes,
        request_json.start_date,
        request_json.finish_date,
        None,
        request_json.export_chart,
        request_json.export_tradingview,
        request_json.export_csv,
        request_json.export_json,
        request_json.fast_mode,
        request_json.benchmark
    )

    return JSONResponse({'message': 'Started backtesting...'}, status_code=202)


@router.post("/cancel")
def cancel_backtest(request_json: CancelRequestJson, authorization: Optional[str] = Header(None)):
    """
    Cancel a backtest process
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    process_manager.cancel_process(request_json.id)
    
    from jesse.models.BacktestSession import update_backtest_session_status
    update_backtest_session_status(request_json.id, 'cancelled')

    return JSONResponse({'message': f'Backtest process with ID of {request_json.id} was requested for termination'},
                        status_code=202)


@router.get("/logs/{session_id}")
def get_logs(session_id: str, token: str = Query(...)):
    """
    Get logs as text for a specific session. Similar to download but returns text content instead of file.
    """
    if not authenticator.is_valid_token(token):
        return authenticator.unauthorized_response()

    try:
        from jesse.modes.data_provider import get_backtest_logs
        content = get_backtest_logs(session_id)

        if content is None:
            return JSONResponse({'error': 'Log file not found'}, status_code=404)

        return JSONResponse({'content': content}, status_code=200)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.get("/download-log/{session_id}")
def download_backtest_log(session_id: str, token: str = Query(...)):
    """
    Download log file for a specific backtest session
    """
    if not authenticator.is_valid_token(token):
        return authenticator.unauthorized_response()

    try:
        from jesse.modes.data_provider import download_backtest_log
        return download_backtest_log(session_id)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.post("/sessions")
def get_backtest_sessions(request_json: GetBacktestSessionsRequestJson = Body(default=GetBacktestSessionsRequestJson()), authorization: Optional[str] = Header(None)):
    """
    Get a list of backtest sessions sorted by most recently updated with pagination
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    # Get sessions from the database with pagination and filters
    sessions = get_sessions(
        limit=request_json.limit, 
        offset=request_json.offset,
        title_search=request_json.title_search,
        status_filter=request_json.status_filter,
        date_filter=request_json.date_filter
    )

    # Transform the sessions using the transformer
    transformed_sessions = [get_backtest_session(session) for session in sessions]

    return JSONResponse({
        'sessions': transformed_sessions,
        'count': len(transformed_sessions)
    })


@router.post("/sessions/{session_id}")
def get_backtest_session_by_id(session_id: str, authorization: Optional[str] = Header(None)):
    """
    Get a single backtest session by ID
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    # Get the session from the database
    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    # Transform the session using the transformer
    transformed_session = get_backtest_session_for_load_more(session)
    transformed_session = jh.clean_infinite_values(transformed_session)

    return JSONResponse({
        'session': transformed_session
    })


@router.post("/update-state")
def update_session_state(request_json: UpdateBacktestSessionStateRequestJson, authorization: Optional[str] = Header(None)):
    """
    Update the state of a backtest session
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    update_backtest_session_state(request_json.id, request_json.state)

    return JSONResponse({
        'message': 'Backtest session state updated successfully'
    })


@router.post("/sessions/{session_id}/remove")
def remove_backtest_session(session_id: str, authorization: Optional[str] = Header(None)):
    """
    Remove a backtest session from the database
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    # Delete the session from the database
    result = delete_backtest_session(session_id)

    if not result:
        return JSONResponse({
            'error': f'Failed to delete session with ID {session_id}'
        }, status_code=500)

    return JSONResponse({
        'message': 'Backtest session removed successfully'
    })


@router.post("/sessions/{session_id}/notes")
def update_session_notes(session_id: str, request_json: UpdateBacktestSessionNotesRequestJson, authorization: Optional[str] = Header(None)):
    """
    Update the notes (title, description, strategy_codes) of a backtest session
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    update_backtest_session_notes(session_id, request_json.title, request_json.description, request_json.strategy_codes)

    return JSONResponse({
        'message': 'Backtest session notes updated successfully'
    })


@router.post("/purge-sessions")
def purge_sessions(request_json: dict = Body(...), authorization: Optional[str] = Header(None)):
    """
    Purge backtest sessions older than specified days
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    
    days_old = request_json.get('days_old', None)
    
    from jesse.models.BacktestSession import purge_backtest_sessions
    deleted_count = purge_backtest_sessions(days_old)
    
    return JSONResponse({
        'message': f'Successfully purged {deleted_count} session(s)',
        'deleted_count': deleted_count
    }, status_code=200)


@router.post("/sessions/{session_id}/chart-data")
def get_backtest_session_chart_data(session_id: str, authorization: Optional[str] = Header(None)):
    """
    Get chart data for a specific backtest session
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    chart_data = jh.clean_infinite_values(json.loads(session.chart_data)) if session.chart_data else None

    return JSONResponse({
        'chart_data': chart_data
    })


@router.post("/sessions/{session_id}/strategy-code")
def get_backtest_session_strategy_codes(session_id: str, authorization: Optional[str] = Header(None)):
    """
    Get strategy codes for a specific backtest session
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    return JSONResponse({
        'strategy_code': json.loads(session.strategy_codes) if session.strategy_codes else {}
    })

