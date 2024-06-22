from starlette.responses import JSONResponse


def get_exchange_supported_symbols(exchange: str) -> JSONResponse:
    arr = ['BTC-USDT', 'ETH-USDT', 'LTC-USDT']

    return JSONResponse({
        'data': arr
    }, status_code=200)
