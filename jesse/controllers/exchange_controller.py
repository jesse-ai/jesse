from typing import Optional
from fastapi import APIRouter, Header
from starlette.responses import JSONResponse

from jesse.modes.import_candles_mode import CandleExchange
from jesse.modes.import_candles_mode.drivers import drivers, driver_names
from jesse.services import auth as authenticator
from jesse.services.redis import sync_redis
from jesse.services.web import ExchangeSupportedSymbolsRequestJson, StoreExchangeApiKeyRequestJson, DeleteExchangeApiKeyRequestJson


router = APIRouter(prefix="/exchange", tags=["Exchange"])


@router.post('/supported-symbols')
def exchange_supported_symbols(request_json: ExchangeSupportedSymbolsRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    return get_exchange_supported_symbols(request_json.exchange)


@router.get('/api-keys')
def get_exchange_api_keys_endpoint(authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes.exchange_api_keys import get_exchange_api_keys
    return get_exchange_api_keys()


@router.post('/api-keys/store')
def store_exchange_api_keys_endpoint(json_request: StoreExchangeApiKeyRequestJson,
                        authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes.exchange_api_keys import store_exchange_api_keys
    return store_exchange_api_keys(
        json_request.exchange, json_request.name, json_request.api_key, json_request.api_secret,
        json_request.additional_fields, json_request.general_notifications_id, json_request.error_notifications_id
    )


@router.post('/api-keys/delete')
def delete_exchange_api_keys_endpoint(json_request: DeleteExchangeApiKeyRequestJson,
                         authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes.exchange_api_keys import delete_exchange_api_keys
    return delete_exchange_api_keys(json_request.id)


def get_exchange_supported_symbols(exchange: str) -> JSONResponse:
    # first try to get from cache
    cache_key = f'exchange-symbols:{exchange}'
    cached_result = sync_redis.get(cache_key)
    if cached_result is not None:
        return JSONResponse({
            'data': eval(cached_result)
        }, status_code=200)

    arr = []

    try:
        driver: CandleExchange = drivers[exchange]()
    except KeyError:
        raise ValueError(f'{exchange} is not a supported exchange. Supported exchanges are: {driver_names}')

    try:
        arr = driver.get_available_symbols()
        # cache successful result for 5 minutes
        sync_redis.setex(cache_key, 300, str(arr))
    except Exception as e:
        return JSONResponse({
            'error': str(e)
        }, status_code=500)

    return JSONResponse({
        'data': arr
    }, status_code=200)
