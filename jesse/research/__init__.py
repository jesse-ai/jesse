from .get_candles import get_candles
from .backtest import backtest
import numpy as np


def store_candles(candles: np.ndarray, exchange: str, symbol: str) -> None:
    from jesse.services.db import store_candles as store_candles_from_list
    import jesse.helpers as jh

    # check if .env file exists
    if not jh.is_jesse_project():
        raise FileNotFoundError(
            'Invalid directory: ".env" file not found. To use Jesse inside notebooks, create notebooks inside the root of a Jesse project.'
        )

    arr = [{
            'id': jh.generate_unique_id(),
            'symbol': symbol,
            'exchange': exchange,
            'timestamp': c[0],
            'open': c[1],
            'close': c[2],
            'high': c[3],
            'low': c[4],
            'volume': c[5]
        } for c in candles]

    store_candles_from_list(arr)
