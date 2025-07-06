from collections import namedtuple

import numpy as np

from jesse.helpers import slice_candles
from jesse_rust import di as di_rust

DI = namedtuple('DI', ['plus', 'minus'])


def di(candles: np.ndarray, period: int = 14, sequential: bool = False) -> DI:
    """
    DI - Directional Indicator

    :param candles: np.ndarray, where columns are expected to be: index 2: close, index 3: high, index 4: low.
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: DI(plus, minus)
    """
    candles = slice_candles(candles, sequential)
    n = len(candles)
    if n < 2:
        if sequential:
            return DI(np.full(n, np.nan), np.full(n, np.nan))
        else:
            return DI(np.nan, np.nan)

    # Use Rust implementation
    plus_DI_arr, minus_DI_arr = di_rust(candles, period)
    if sequential:
        return DI(plus_DI_arr, minus_DI_arr)
    else:
        return DI(plus_DI_arr[-1], minus_DI_arr[-1])
