from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from jesse.services import auth as authenticator

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.post("/posthog/status")
def get_posthog_status(authorization: Optional[str] = Header(None)):
    """
    Get PostHog error tracking status
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services.posthog import get_posthog_service

    posthog_service = get_posthog_service()

    return JSONResponse(
        {
            "error_tracking_enabled": posthog_service._client is not None,
            "initialized": posthog_service._client is not None,
            "message": "PostHog status retrieved successfully",
        },
        status_code=200,
    )


@router.post("/posthog/start")
def start_posthog(authorization: Optional[str] = Header(None)):
    """
    Start PostHog error tracking and identify user
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services.posthog import get_posthog_service

    try:
        posthog_service = get_posthog_service()


        # check if posthog service is already initialized
        if posthog_service._client is not None:
            return JSONResponse({
                'enabled': True,
                'message': 'PostHog Monitoring already started'
            }, status_code=200)

        # Initialize posthog service
        posthog_service._initialize()

        # Get system info and identify user
        import jesse.helpers as jh
        from jesse.services.general_info import get_general_info
        info = get_general_info(has_live=jh.has_live_trade_plugin())
        system_info = info.get("system_info", {})

        posthog_service.identify_user(authorization, system_info)

        return JSONResponse({
            'enabled': True,
            'message': 'PostHog error tracking started and user identified successfully'
        }, status_code=200)

    except Exception as e:
        return JSONResponse({
            'error': str(e),
            'message': 'Failed to start PostHog error tracking'
        }, status_code=500)


@router.post("/posthog/stop")
def stop_posthog(authorization: Optional[str] = Header(None)):
    """
    Stop PostHog error tracking
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services.posthog import get_posthog_service

    try:
        posthog_service = get_posthog_service()
        
        posthog_service.shutdown()
            
        return JSONResponse({
            'enabled': False,
            'message': 'PostHog error tracking stopped successfully'
        }, status_code=200)

    except Exception as e:
        return JSONResponse({
            'error': str(e),
            'message': 'Failed to stop PostHog error tracking'
        }, status_code=500)


@router.post("/posthog/panic-test")
def test_posthog_exception(authorization: Optional[str] = Header(None)):
    """
    Test PostHog exception capturing by triggering a test exception
    """
    raise RuntimeError("This is a test exception")


@router.post("/posthog/python-auto-capture-test")
def test_python_auto_capture(authorization: Optional[str] = Header(None)):
    """
    Test PostHog's Python auto-capture by raising an exception outside FastAPI handling
    """
    import threading
    import time
    
    def raise_in_background():
        time.sleep(1)  # Wait a bit
        raise RuntimeError("This should be auto-captured by PostHog Python SDK")
    
    # Start a background thread that will raise an unhandled exception
    thread = threading.Thread(target=raise_in_background)
    thread.daemon = True
    thread.start()
    
    return {"message": "Background thread started, exception should be auto-captured by PostHog"}
