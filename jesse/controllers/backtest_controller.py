from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse, FileResponse
import json
from jesse.services.auth import require_auth, require_auth_any, require_auth_token
from jesse.services.multiprocessing import process_manager
from jesse.services.web import BacktestRequestJson, CancelRequestJson, UpdateBacktestSessionStateRequestJson, GetBacktestSessionsRequestJson, UpdateBacktestSessionNotesRequestJson
import jesse.helpers as jh
from jesse.models.BacktestSession import (
    get_backtest_sessions as get_sessions,
    update_backtest_session_state,
    update_backtest_session_notes,
    delete_backtest_session,
    get_backtest_session_by_id as get_backtest_session_by_id_from_db,
    update_backtest_session_status,
    purge_backtest_sessions
)
from jesse.services.transformers import get_backtest_session, get_backtest_session_for_load_more
from jesse.modes.backtest_mode import run as run_backtest
from jesse.modes.data_provider import get_backtest_logs, download_backtest_log
import os



router = APIRouter(prefix="/backtest", tags=["Backtest"])


@router.post("", dependencies=[Depends(require_auth)])
def backtest(request_json: BacktestRequestJson):
    """
    Start a backtest process
    """

    jh.validate_cwd()

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
        request_json.benchmark,
        request_json.theme
    )

    return JSONResponse({'message': 'Started backtesting...'}, status_code=202)


BACKTEST_CHART_NAMES = ['equity_curve', 'cumulative_returns', 'drawdown', 'underwater', 'monthly_heatmap', 'monthly_distribution', 'trade_pnl']


@router.get("/sessions/{session_id}/charts-image", dependencies=[Depends(require_auth_any)])
def get_charts_image(
    session_id: str,
    chart: str,
):
    """
    Serve a chart PNG image for a specific backtest session.
    chart param must be one of: equity_curve, drawdown, underwater, monthly_heatmap, monthly_distribution, trade_pnl
    """

    if chart not in BACKTEST_CHART_NAMES:
        return JSONResponse({'error': f'Unknown chart name: {chart}'}, status_code=400)

    charts_folder = os.path.abspath('storage/backtest-charts')
    path = os.path.join(charts_folder, f'{session_id}_{chart}.png')

    if not os.path.exists(path):
        return JSONResponse({'error': 'Chart image not yet available'}, status_code=404)

    return FileResponse(path, media_type='image/png')


@router.post("/cancel", dependencies=[Depends(require_auth)])
def cancel_backtest(request_json: CancelRequestJson):
    """
    Cancel a backtest process
    """

    process_manager.cancel_process(request_json.id)
    
    update_backtest_session_status(request_json.id, 'cancelled')

    return JSONResponse({'message': f'Backtest process with ID of {request_json.id} was requested for termination'},
                        status_code=202)


@router.get("/logs/{session_id}", dependencies=[Depends(require_auth_token)])
def get_logs(session_id: str):
    """
    Get logs as text for a specific session. Similar to download but returns text content instead of file.
    """

    try:
        content = get_backtest_logs(session_id)

        if content is None:
            return JSONResponse({'error': 'Log file not found'}, status_code=404)

        return JSONResponse({'content': content}, status_code=200)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.get("/download-log/{session_id}", dependencies=[Depends(require_auth_token)])
def download_backtest_log_handler(session_id: str):
    """
    Download log file for a specific backtest session
    """

    try:
        return download_backtest_log(session_id)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.post("/sessions", dependencies=[Depends(require_auth)])
def get_backtest_sessions(request_json: GetBacktestSessionsRequestJson = Body(default=GetBacktestSessionsRequestJson())):
    """
    Get a list of backtest sessions sorted by most recently updated with pagination
    """

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


@router.post("/sessions/{session_id}", dependencies=[Depends(require_auth)])
def get_backtest_session_by_id(session_id: str):
    """
    Get a single backtest session by ID
    """

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


@router.post("/update-state", dependencies=[Depends(require_auth)])
def update_session_state(request_json: UpdateBacktestSessionStateRequestJson):
    """
    Update the state of a backtest session
    """

    update_backtest_session_state(request_json.id, request_json.state)

    return JSONResponse({
        'message': 'Backtest session state updated successfully'
    })


@router.post("/sessions/{session_id}/remove", dependencies=[Depends(require_auth)])
def remove_backtest_session(session_id: str):
    """
    Remove a backtest session from the database
    """

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


@router.post("/sessions/{session_id}/notes", dependencies=[Depends(require_auth)])
def update_session_notes(session_id: str, request_json: UpdateBacktestSessionNotesRequestJson):
    """
    Update the notes (title, description, strategy_codes) of a backtest session
    """

    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    update_backtest_session_notes(session_id, request_json.title, request_json.description, request_json.strategy_codes)

    return JSONResponse({
        'message': 'Backtest session notes updated successfully'
    })


@router.post("/purge-sessions", dependencies=[Depends(require_auth)])
def purge_sessions(request_json: dict = Body(...)):
    """
    Purge backtest sessions older than specified days
    """
    
    days_old = request_json.get('days_old', None)
    
    deleted_count = purge_backtest_sessions(days_old)
    
    return JSONResponse({
        'message': f'Successfully purged {deleted_count} session(s)',
        'deleted_count': deleted_count
    }, status_code=200)


@router.post("/sessions/{session_id}/chart-data", dependencies=[Depends(require_auth)])
def get_backtest_session_chart_data(session_id: str):
    """
    Get chart data for a specific backtest session
    """

    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    chart_data = jh.clean_nan_values(jh.clean_infinite_values(json.loads(session.chart_data))) if session.chart_data else None

    return JSONResponse({
        'chart_data': chart_data
    })


@router.post("/sessions/{session_id}/strategy-code", dependencies=[Depends(require_auth)])
def get_backtest_session_strategy_codes(session_id: str):
    """
    Get strategy codes for a specific backtest session
    """

    session = get_backtest_session_by_id_from_db(session_id)

    if not session:
        return JSONResponse({
            'error': f'Session with ID {session_id} not found'
        }, status_code=404)

    return JSONResponse({
        'strategy_code': json.loads(session.strategy_codes) if session.strategy_codes else {}
    })

