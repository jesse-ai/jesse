from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, slice_candles
from jesse.indicators.ma import ma
from jesse.indicators.mean_ad import mean_ad
from jesse.indicators.median_ad import median_ad

def moving_std(source: np.ndarray, window: int) -> np.ndarray:
    n = len(source)
    stdArr = np.empty_like(source)
    if n < window:
        # Vectorized cumulative standard deviation for all indices
        cumsum = np.cumsum(source)
        cumsum2 = np.cumsum(source**2)
        counts = np.arange(1, n + 1)
        means = cumsum / counts
        variances = cumsum2 / counts - means**2
        stdArr[:] = np.sqrt(np.maximum(variances, 0))
    else:
        # For indices with less than a full window, use cumulative statistics
        cumsum_init = np.cumsum(source[:window-1])
        cumsum2_init = np.cumsum(source[:window-1]**2)
        counts_init = np.arange(1, window)
        means_init = cumsum_init / counts_init
        variances_init = cumsum2_init / counts_init - means_init**2
        stdArr[:window-1] = np.sqrt(np.maximum(variances_init, 0))
        
        # For full windows, use sliding window view and compute standard deviation
        sw = np.lib.stride_tricks.sliding_window_view(source, window_shape=window)
        stdArr[window-1:] = np.std(sw, axis=1)
    return stdArr


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

    if matype == 24 or matype == 29:
        mean = ma(candles, period=max_period, matype=matype, source_type=source_type, sequential=True)
    else:
        mean = ma(source, period=max_period, matype=matype, sequential=True)

    if devtype == 0:
       stdDev = moving_std(source, max_period)
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
