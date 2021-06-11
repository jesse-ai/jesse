from .get_candles import get_candles
from jesse.services.db import store_candles as store_candles_from_list
import jesse.helpers as jh
import numpy as np


def init() -> None:
    from pydoc import locate
    import os
    import sys

    # fix directory issue
    sys.path.insert(0, os.getcwd())

    ls = os.listdir('.')
    is_jesse_project = 'strategies' in ls and 'config.py' in ls and 'storage' in ls and 'routes.py' in ls

    if not is_jesse_project:
        print(
            jh.color(
                'Invalid directory. To use Jesse inside notebooks, create notebooks inside the root of a Jesse project.',
                'red'
            )
        )

    if is_jesse_project:
        local_config = locate('config.config')
        from jesse.config import set_config
        set_config(local_config)


def store_candles(candles: np.ndarray, exchange: str, symbol: str) -> None:
    arr = []

    for c in candles:
        arr.append({
            'id': jh.generate_unique_id(),
            'symbol': symbol,
            'exchange': exchange,
            'timestamp': c[0],
            'open': c[1],
            'close': c[2],
            'high': c[3],
            'low': c[4],
            'volume': c[5]
        })

    store_candles_from_list(arr)
