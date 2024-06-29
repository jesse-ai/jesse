from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, slice_candles


def nma(candles: np.ndarray, period: int = 40, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    Natural Moving Average

    :param candles: np.ndarray
    :param period: int - default: 40
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """

    # Accept normal array too.
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    res = nma_fast(source, period)

    return res if sequential else res[-1]

@njit(cache=True)
def nma_fast(source, period):
    # Ensure source values are positive before taking log
    source = np.clip(source, a_min=1e-10, a_max=None)
    ln = np.log(source) * 1000
    newseries = np.full_like(source, np.nan)

    for j in range(period + 1, source.shape[0]):
        num = 0.0
        denom = 0.0
        for i in range(period):
            oi = np.abs(ln[j - i] - ln[j - i - 1])
            num += oi * (np.sqrt(i + 1) - np.sqrt(i))
            denom += oi

        ratio = num / denom if denom != 0 else 0
        newseries[j] = (source[j - i] * ratio) + (source[j - i - 1] * (1 - ratio))

    return newseries
