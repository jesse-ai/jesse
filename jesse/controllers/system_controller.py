from typing import Optional
from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from jesse.services import auth as authenticator
from jesse.services.web import FeedbackRequestJson, ReportExceptionRequestJson, HelpSearchRequestJson
from jesse.services.multiprocessing import process_manager
import jesse.helpers as jh

router = APIRouter(prefix="/system", tags=["System"])


@router.post("/feedback")
def feedback(json_request: FeedbackRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Send feedback to the Jesse team
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import jesse_trade
    return jesse_trade.feedback(json_request.description, json_request.email)


@router.post("/report-exception")
def report_exception(json_request: ReportExceptionRequestJson,
                     authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Report an exception to the Jesse team
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import jesse_trade
    
    return jesse_trade.report_exception(
        json_request.description,
        json_request.traceback,
        json_request.mode,
        json_request.attach_logs,
        json_request.session_id,
        json_request.email,
        has_live=jh.has_live_trade_plugin()
    )


@router.post("/general-info")
def general_info(authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Get general information about the system
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services.general_info import get_general_info

    try:
        data = get_general_info(has_live=jh.has_live_trade_plugin())
    except Exception as e:
        jh.error(str(e))
        return JSONResponse({
            'error': str(e)
        }, status_code=500)

    return JSONResponse(
        data,
        status_code=200
    )


@router.post("/active-workers")
def active_workers(authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Get a list of active workers
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    return JSONResponse({
        'data': list(process_manager.active_workers)
    }, status_code=200)


@router.post("/help-search")
def help_search(json_request: HelpSearchRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Proxy endpoint for help center search to avoid CORS issues
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    
    import requests
    from jesse.info import JESSE_API_URL
    from jesse.services.auth import get_access_token
    
    try:
        url = f'{JESSE_API_URL}/help/search?item={json_request.query}'
        
        access_token = get_access_token()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*'
        }
        
        if access_token:
            headers['Authorization'] = f'Bearer {access_token}'
        
        res = requests.get(url, headers=headers, timeout=10)
        
        if res.status_code == 200:
            return JSONResponse(res.json(), status_code=200)
        else:
            return JSONResponse({
                'error': f'Search request failed with status {res.status_code}'
            }, status_code=res.status_code)
    except Exception as e:
        return JSONResponse({
            'error': str(e)
        }, status_code=500)
