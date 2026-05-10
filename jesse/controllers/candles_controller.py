from jesse.services.auth import require_auth
from typing import Optional
from fastapi import APIRouter, Header, Depends
from starlette.responses import JSONResponse
from jesse.repositories import candle_repository
from jesse.services.multiprocessing import process_manager
from jesse.services.web import ImportCandlesRequestJson, CancelRequestJson, GetCandlesRequestJson, DeleteCandlesRequestJson, PurgeCandlesRequestJson
import jesse.helpers as jh

router = APIRouter(prefix="/candles", tags=["Candles"])


@router.post("/import")
def import_candles(request_json: ImportCandlesRequestJson, authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)) -> JSONResponse:
    """
    Import candles for a specific exchange and symbol
    """
    jh.validate_cwd()


    from jesse.modes import import_candles_mode

    process_manager.add_task(
        import_candles_mode.run, 
        request_json.id, 
        request_json.exchange, 
        request_json.symbol,
        request_json.start_date
    )

    return JSONResponse({'message': 'Started importing candles...'}, status_code=202)


@router.post("/cancel-import")
def cancel_import_candles(request_json: CancelRequestJson, authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)):
    """
    Cancel an import candles process
    """

    process_manager.cancel_process(request_json.id)

    return JSONResponse({'message': f'Candles process with ID of {request_json.id} was requested for termination'},
                        status_code=202)


@router.post("/clear-cache")
def clear_candles_database_cache(authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)):
    """
    Clear the candles database cache
    """

    from jesse.services.cache import cache
    cache.flush()

    return JSONResponse({
        'status': 'success',
        'message': 'Candles database cache cleared successfully',
    }, status_code=200)


@router.post("/get")
def get_candles(json_request: GetCandlesRequestJson, authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)) -> JSONResponse:
    """
    Get candles for a specific exchange, symbol, and timeframe
    """

    jh.validate_cwd()

    from jesse.modes.data_provider import get_candles as gc

    arr = gc(json_request.exchange, json_request.symbol, json_request.timeframe)

    return JSONResponse({
        'id': json_request.id,
        'data': arr
    }, status_code=200)


@router.post("/existing")
def get_existing_candles(authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)) -> JSONResponse:
    """
    Get all existing candles in the database
    """
    
    try:
        data = candle_repository.get_existing_candles()
        return JSONResponse({'data': data}, status_code=200)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.post("/delete")
def delete_candles(json_request: DeleteCandlesRequestJson, authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)) -> JSONResponse:
    """
    Delete candles for a specific exchange and symbol
    """

    try:
        candle_repository.delete_candles_from_db(json_request.exchange, json_request.symbol)
        return JSONResponse({'message': 'Candles deleted successfully'}, status_code=200)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.post("/purge")
def purge_candles(json_request: PurgeCandlesRequestJson, authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)) -> JSONResponse:
    """
    Delete all candles for the given list of exchanges
    """

    try:
        deleted_count = candle_repository.purge_candles_by_exchanges(json_request.exchanges)
        return JSONResponse({'message': f'Purged candles for {len(json_request.exchanges)} exchange(s)', 'deleted_count': deleted_count}, status_code=200)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)
