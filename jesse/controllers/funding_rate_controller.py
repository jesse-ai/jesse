from typing import Optional
from fastapi import APIRouter, Header
from starlette.responses import JSONResponse

from jesse.services import auth as authenticator
from jesse.services.multiprocessing import process_manager
from jesse.services.web import ImportCandlesRequestJson, CancelRequestJson, GetCandlesRequestJson, DeleteCandlesRequestJson
import jesse.helpers as jh

router = APIRouter(prefix="/funding-rate", tags=["Funding Rate"])


@router.post("/import")
def import_funding_rates(request_json: ImportCandlesRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Import funding rates for a specific exchange and symbol
    """
    jh.validate_cwd()

    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    # import the research helper that runs funding rates import
    from jesse.research import import_funding_rates as ifr

    process_manager.add_task(
        ifr.import_funding_rates,
        request_json.id,
        request_json.exchange,
        request_json.symbol,
        request_json.start_date
    )

    return JSONResponse({'message': 'Started importing funding rates...'}, status_code=202)


@router.post("/cancel-import")
def cancel_import_candles(request_json: CancelRequestJson, authorization: Optional[str] = Header(None)):
    """
    Cancel an import candles process
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    process_manager.cancel_process(request_json.id)

    return JSONResponse({'message': f'Candles process with ID of {request_json.id} was requested for termination'},
                        status_code=202)


@router.post("/clear-cache")
def clear_candles_database_cache(authorization: Optional[str] = Header(None)):
    """
    Clear the candles database cache
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services.cache import cache
    cache.flush()

    return JSONResponse({
        'status': 'success',
        'message': 'Candles database cache cleared successfully',
    }, status_code=200)


@router.post("/get")
def get_candles(json_request: GetCandlesRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Get candles for a specific exchange, symbol, and timeframe
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    jh.validate_cwd()

    from jesse.modes.data_provider import get_candles as gc

    arr = gc(json_request.exchange, json_request.symbol, json_request.timeframe)

    return JSONResponse({
        'id': json_request.id,
        'data': arr
    }, status_code=200)
