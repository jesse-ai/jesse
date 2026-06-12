from typing import Optional
from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
import psutil
import os
import requests

from jesse.services import auth as authenticator
from jesse.services.web import FeedbackRequestJson, ReportExceptionRequestJson, HelpSearchRequestJson
from jesse.services.multiprocessing import process_manager
from jesse.services import jesse_trade
from jesse.services.general_info import get_general_info
from jesse.services.auth import get_access_token
from jesse.info import JESSE_API_URL
from jesse.version import __version__ as jesse_version
from jesse.models import BacktestSession, OptimizationSession, LiveSession, MonteCarloSession, SignificanceTestSession
import jesse.helpers as jh

router = APIRouter(prefix="/system", tags=["System"])


@router.post("/feedback")
def feedback(json_request: FeedbackRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Send feedback to the Jesse team
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    return jesse_trade.feedback(json_request.description, json_request.email)


@router.post("/report-exception")
def report_exception(json_request: ReportExceptionRequestJson,
                     authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Report an exception to the Jesse team
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

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


@router.get("/system-info")
def system_info(authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Get system info (CPU, RAM, version, etc)
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    strategies_path = os.getcwd() + "/strategies/"
    try:
        strategies = list(sorted([name for name in os.listdir(strategies_path) if os.path.isdir(strategies_path + name) and not name.startswith('.')]))
        if "__pycache__" in strategies:
            strategies.remove("__pycache__")
        strategy_count = len(strategies)
    except Exception:
        strategy_count = 0

    return JSONResponse({
        'cpu_cores': psutil.cpu_count(logical=True),
        'cpu_usage_percent': psutil.cpu_percent(interval=0.1),
        'ram_usage_percent': psutil.virtual_memory().percent,
        'ram_total_gb': round(psutil.virtual_memory().total / (1024 ** 3), 2),
        'ram_used_gb': round(psutil.virtual_memory().used / (1024 ** 3), 2),
        'jesse_version': jesse_version,
        'strategy_count': strategy_count
    }, status_code=200)


@router.get("/user-activity")
def user_activity(authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Get user activity stats (backtests, optimizations, etc)
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    current_timestamp = jh.now_to_timestamp(True)
    day_ago = current_timestamp - (24 * 60 * 60 * 1000)
    week_ago = current_timestamp - (7 * 24 * 60 * 60 * 1000)

    def get_counts(model):
        try:
            all_time = model.select().where(model.status != 'draft').count()
            last_24h = model.select().where((model.status != 'draft') & (model.created_at >= day_ago)).count()
            last_7d = model.select().where((model.status != 'draft') & (model.created_at >= week_ago)).count()
            return {'all_time': all_time, 'last_24h': last_24h, 'last_7d': last_7d}
        except Exception:
            return {'all_time': 0, 'last_24h': 0, 'last_7d': 0}

    try:
        backtests = get_counts(BacktestSession)
        optimizations = get_counts(OptimizationSession)
        live_sessions = get_counts(LiveSession)
        monte_carlo = get_counts(MonteCarloSession)
        significance_tests = get_counts(SignificanceTestSession)
    except Exception as e:
        jh.error(str(e))
        backtests = optimizations = live_sessions = monte_carlo = significance_tests = {'all_time': 0, 'last_24h': 0, 'last_7d': 0}

    return JSONResponse({
        'backtests': backtests,
        'optimizations': optimizations,
        'live_sessions': live_sessions,
        'monte_carlo': monte_carlo,
        'significance_tests': significance_tests
    }, status_code=200)
