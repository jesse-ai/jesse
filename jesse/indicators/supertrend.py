from collections import namedtuple

import numpy as np
from numba import njit

from jesse.helpers import slice_candles

SuperTrend = namedtuple('SuperTrend', ['trend', 'changed'])


def supertrend(candles: np.ndarray, period: int = 10, factor: float = 3, sequential: bool = False) -> SuperTrend:
    """
    SuperTrend indicator optimized with numba and loop-based calculations.
    :param candles: np.ndarray - candle data
    :param period: period for ATR calculation
    :param factor: multiplier for the bands
    :param sequential: if True, returns full arrays; else, returns last value
    :return: SuperTrend named tuple with trend and changed arrays/values
    """
    candles = slice_candles(candles, sequential)
    atr = atr_loop(candles[:, 3], candles[:, 4], candles[:, 2], period)
    super_trend, changed = supertrend_fast(candles, atr, factor, period)
    if sequential:
        return SuperTrend(super_trend, changed)
    else:
        return SuperTrend(super_trend[-1], changed[-1])


@njit(cache=True)
def atr_loop(high, low, close, period):
    n = len(close)
    tr = np.empty(n, dtype=np.float64)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        diff1 = high[i] - low[i]
        diff2 = np.abs(high[i] - close[i-1])
        diff3 = np.abs(low[i] - close[i-1])
        # manual max of the three differences
        if diff1 >= diff2 and diff1 >= diff3:
            tr[i] = diff1
        elif diff2 >= diff1 and diff2 >= diff3:
            tr[i] = diff2
        else:
            tr[i] = diff3

    atr = np.empty(n, dtype=np.float64)
    # Set initial values to NaN for indices before period-1
    for i in range(period - 1):
        atr[i] = np.nan
    # First ATR value is the simple average of the first 'period' TR values
    sum_init = 0.0
    for i in range(period):
        sum_init += tr[i]
    atr[period - 1] = sum_init / period
    # Recursive ATR calculation
    for i in range(period, n):
        atr[i] = ((atr[i-1] * (period - 1)) + tr[i]) / period
    return atr


@njit(cache=True)
def supertrend_fast(candles, atr, factor, period):
    n = len(candles)
    super_trend = np.zeros(n, dtype=np.float64)
    changed = np.zeros(n, dtype=np.int8)

    # Precompute basic bands and initialize band arrays
    upper_basic = np.empty(n, dtype=np.float64)
    lower_basic = np.empty(n, dtype=np.float64)
    upper_band = np.empty(n, dtype=np.float64)
    lower_band = np.empty(n, dtype=np.float64)

    for i in range(n):
        mid = (candles[i, 3] + candles[i, 4]) / 2.0
        upper_basic[i] = mid + factor * atr[i]
        lower_basic[i] = mid - factor * atr[i]
        upper_band[i] = upper_basic[i]
        lower_band[i] = lower_basic[i]

    # Set the initial supertrend for index period-1
    idx = period - 1
    if candles[idx, 2] <= upper_band[idx]:
        super_trend[idx] = upper_band[idx]
    else:
        super_trend[idx] = lower_band[idx]
    changed[idx] = 0

    # Combined loop: update bands and compute supertrend
    for i in range(period, n):
        p = i - 1
        prevClose = candles[p, 2]
        
        # Update upper_band
        if prevClose <= upper_band[p]:
            if upper_basic[i] < upper_band[p]:
                upper_band[i] = upper_basic[i]
            else:
                upper_band[i] = upper_band[p]
        else:
            upper_band[i] = upper_basic[i]

        # Update lower_band
        if prevClose >= lower_band[p]:
            if lower_basic[i] > lower_band[p]:
                lower_band[i] = lower_basic[i]
            else:
                lower_band[i] = lower_band[p]
        else:
            lower_band[i] = lower_basic[i]

        # Compute current supertrend based on previous supertrend value
        if super_trend[p] == upper_band[p]:
            if candles[i, 2] <= upper_band[i]:
                super_trend[i] = upper_band[i]
                changed[i] = 0
            else:
                super_trend[i] = lower_band[i]
                changed[i] = 1
        else:  # super_trend[p] equals lower_band[p]
            if candles[i, 2] >= lower_band[i]:
                super_trend[i] = lower_band[i]
                changed[i] = 0
            else:
                super_trend[i] = upper_band[i]
                changed[i] = 1

    return super_trend, changed
