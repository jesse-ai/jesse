from typing import Union

import numpy as np
import talib
from numba import njit

from jesse.helpers import get_candle_source, slice_candles
from jesse.indicators.ma import ma
from jesse.indicators.mean_ad import mean_ad
from jesse.indicators.median_ad import median_ad


def vlma(candles: np.ndarray, min_period: int = 5, max_period: int = 50, matype: int = 0, devtype: int = 0, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Variable Length Moving Average

    :param candles: np.ndarray
    :param min_period: int - default: 5
    :param max_period: int - default: 50
    :param matype: int - default: 0
    :param devtype: int - default: 0
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

    mean = ma(source, period=max_period, matype=matype, sequential=True)

    if devtype == 0:
       stdDev = talib.STDDEV(source, max_period)
    elif devtype == 1:
       stdDev = mean_ad(source, max_period, sequential=True)
    elif devtype == 2:
       stdDev = median_ad(source, max_period, sequential=True)

    a = mean - (1.75 * stdDev)
    b = mean - (0.25 * stdDev)
    c = mean + (0.25 * stdDev)
    d = mean + (1.75 * stdDev)

    res = vlma_fast(source, a, b, c, d , min_period, max_period)

    return res if sequential else res[-1]


@njit(cache=True)
def vlma_fast(source, a, b, c, d, min_period, max_period):
    newseries = np.copy(source)
    period = np.zeros_like(source)
    for i in range(1, source.shape[0]):
        nz_period = period[i - 1] if period[i - 1] != 0 else max_period
        period[i] = nz_period + 1 if b[i] <= source[i] <= c[i] else nz_period - 1 if source[i] < a[i] or source[i] > d[i] else nz_period
        period[i] = max(min(period[i], max_period), min_period)
        sc = 2 / (period[i] + 1)
        newseries[i] = (source[i] * sc) + ((1 - sc) * newseries[i - 1])
    return newseries
