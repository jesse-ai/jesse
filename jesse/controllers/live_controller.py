from typing import Optional
from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from jesse.services import auth as authenticator
from jesse.services.multiprocessing import process_manager
from jesse.services.web import LiveRequestJson, LiveCancelRequestJson, GetLogsRequestJson, GetOrdersRequestJson
import jesse.helpers as jh
from jesse.models.LiveSession import get_live_sessions, get_live_session_by_id, update_live_session_status
from jesse.services.transformers import get_live_session

router = APIRouter(prefix="/live", tags=["Live Trading"])


@router.post("")
def live(request_json: LiveRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Start live trading
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    jh.validate_cwd()

    trading_mode = 'livetrade' if request_json.paper_mode is False else 'papertrade'

    # execute live session
    from jesse_live import live_mode
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


@router.get("/sessions")
def get_sessions(authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Get sessions for live trading
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    sessions = get_live_sessions()
    # Transform the sessions using the transformer
    transformed_sessions = [get_live_session(session) for session in sessions]
    return JSONResponse({
        'sessions': transformed_sessions
    })

@router.post("/cancel")
def cancel_live(request_json: LiveCancelRequestJson, authorization: Optional[str] = Header(None)):
    """
    Cancel live trading
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    # check if the session is running
    session = get_live_session_by_id(request_json.id)
    if session.status != 'running':
        return JSONResponse({'message': f'Live process with ID of {request_json.id} is not running.'}, status_code=400)
    update_live_session_status(request_json.id, 'terminated')

    process_manager.cancel_process(request_json.id)

    return JSONResponse({'message': f'Live process with ID of {request_json.id} terminated.'}, status_code=200)


@router.post('/logs')
def get_logs(json_request: GetLogsRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Get logs for a live trading session
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse_live.services.data_provider import get_logs as gl

    arr = gl(json_request.id, json_request.type, json_request.start_time)

    return JSONResponse({
        'id': json_request.id,
        'data': arr
    }, status_code=200)


@router.post('/orders')
def get_orders(json_request: GetOrdersRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Get orders for a live trading session
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse_live.services.data_provider import get_orders as go

    arr = go(json_request.session_id)

    return JSONResponse({
        'id': json_request.id,
        'data': arr
    }, status_code=200)
