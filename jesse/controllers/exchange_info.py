from starlette.responses import JSONResponse

from jesse.modes.import_candles_mode import CandleExchange
from jesse.modes.import_candles_mode.drivers import drivers, driver_names


def get_exchange_supported_symbols(exchange: str) -> JSONResponse:
    arr = []

    try:
        driver: CandleExchange = drivers[exchange]()
    except KeyError:
        raise ValueError(f'{exchange} is not a supported exchange. Supported exchanges are: {driver_names}')

    try:
        arr = driver.get_available_symbols()
    except Exception as e:
        return JSONResponse({
            'error': str(e)
        }, status_code=500)

    return JSONResponse({
        'data': arr
    }, status_code=200)
