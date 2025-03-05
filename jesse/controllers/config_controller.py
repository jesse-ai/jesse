from typing import Optional
from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from jesse.services import auth as authenticator
from jesse.services.web import ConfigRequestJson

# Check if the live trade plugin is installed
try:
    import jesse_live
    HAS_LIVE_TRADE_PLUGIN = True
except ImportError:
    HAS_LIVE_TRADE_PLUGIN = False

router = APIRouter(prefix="/config", tags=["Configuration"])


@router.post("/get")
def get_config(json_request: ConfigRequestJson, authorization: Optional[str] = Header(None)):
    """
    Get the current configuration
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes.data_provider import get_config as gc

    return JSONResponse({
        'data': gc(json_request.current_config, has_live=HAS_LIVE_TRADE_PLUGIN)
    }, status_code=200)


@router.post("/update")
def update_config(json_request: ConfigRequestJson, authorization: Optional[str] = Header(None)):
    """
    Update the configuration
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes.data_provider import update_config as uc

    uc(json_request.current_config)

    return JSONResponse({'message': 'Updated configurations successfully'}, status_code=200)
