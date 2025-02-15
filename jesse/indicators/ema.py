from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, slice_candles


@njit(cache=True)
def _ema(source: np.ndarray, period: int) -> np.ndarray:
    """
    Compute the Exponential Moving Average using a loop.
    """
    n = len(source)
    result = np.full(n, np.nan)
    if n < period:
        return result
    alpha = 2 / (period + 1)
    # Initialize EMA with the simple average of the first "period" values
    initial = np.mean(source[:period])
    result[period - 1] = initial
    prev = initial
    for i in range(period, n):
        current = alpha * source[i] + (1 - alpha) * prev
        result[i] = current
        prev = current
    return result

def ema(candles: np.ndarray, period: int = 5, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    EMA - Exponential Moving Average using Numba for optimization

    :param candles: np.ndarray
    :param period: int - default: 5
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    result = _ema(source, period)
    return result if sequential else result[-1]
