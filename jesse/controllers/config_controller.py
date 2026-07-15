from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from jesse.services.auth import require_auth
from jesse.services.web import ConfigRequestJson
import jesse.helpers as jh

router = APIRouter(prefix="/config", tags=["Configuration"], dependencies=[Depends(require_auth)])


@router.post("/get")
def get_config(json_request: ConfigRequestJson):
    """
    Get the current configuration
    """

    from jesse.modes.data_provider import get_config as gc

    return JSONResponse({
        'data': gc(json_request.current_config, has_live=jh.has_live_trade_plugin())
    }, status_code=200)


@router.post("/update")
def update_config(json_request: ConfigRequestJson):
    """
    Update the configuration
    """

    from jesse.modes.data_provider import update_config as uc

    uc(json_request.current_config)

    return JSONResponse({'message': 'Updated configurations successfully'}, status_code=200)
