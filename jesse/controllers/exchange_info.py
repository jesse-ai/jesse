from starlette.responses import JSONResponse

from jesse.modes.import_candles_mode import CandleExchange
from jesse.modes.import_candles_mode.drivers import drivers, driver_names
from jesse.services.redis import sync_redis


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
