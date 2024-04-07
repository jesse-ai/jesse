from typing import Union

import numpy as np
try:
    from numba import njit
except ImportError:
    njit = lambda a : a

from jesse.helpers import get_candle_source, same_length, slice_candles


def cg(candles: np.ndarray, period: int = 10, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Center of Gravity (CG)

    :param candles: np.ndarray
    :param period: int - default: 10
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    res = go_fast(source, period)

    return same_length(candles, res) if sequential else res[-1]


@njit
def go_fast(source, period):  # Function is compiled to machine code when called the first time
    res = np.full_like(source, fill_value=np.nan)
    for i in range(source.size):
        if i > period:
            num = 0
            denom = 0
            for count in range(period - 1):
                close = source[i - count]
                if not np.isnan(close):
                    num += (1 + count) * close
                    denom += close
            result = -num / denom if denom != 0 else 0
            res[i] = result
    return res
