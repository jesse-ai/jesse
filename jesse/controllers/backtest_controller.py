from typing import Optional
from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse, FileResponse

from jesse.services import auth as authenticator
from jesse.services.multiprocessing import process_manager
from jesse.services.web import BacktestRequestJson, CancelRequestJson
import jesse.helpers as jh

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

