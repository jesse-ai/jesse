from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import slice_candles


def chop(candles: np.ndarray, period: int = 14, scalar: float = 100, drift: int = 1, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    Choppiness Index (CHOP)

    :param candles: np.ndarray
    :param period: int - default: 14
    :param scalar: float - default: 100
    :param drift: int - default: 1
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    # Preprocess candles using original slicing
    candles = slice_candles(candles, sequential)
    res = _chop_numba(candles, period, scalar, drift)
    return res if sequential else res[-1]


@njit(cache=True)
def _chop_numba(candles, period, scalar, drift):
    n = candles.shape[0]
    # Extract the necessary candle values
    close = candles[:, 2]
    high = candles[:, 3]
    low = candles[:, 4]

    # Compute True Range (TR)
    tr = np.empty(n, dtype=np.float64)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        d1 = high[i] - low[i]
        d2 = abs(high[i] - close[i - 1])
        d3 = abs(low[i] - close[i - 1])
        if d1 >= d2 and d1 >= d3:
            tr[i] = d1
        elif d2 >= d1 and d2 >= d3:
            tr[i] = d2
        else:
            tr[i] = d3

    # Compute Average True Range (ATR)
    atr = np.empty(n, dtype=np.float64)
    if drift == 1:
        for i in range(n):
            atr[i] = tr[i]
    else:
        # Set initial values to NaN for indices before drift - 1
        for i in range(drift - 1):
            atr[i] = np.nan
        # Compute initial ATR as the average of the first 'drift' TR values
        total = 0.0
        for i in range(drift):
            total += tr[i]
        initial_atr = total / drift
        atr[drift - 1] = initial_atr
        for i in range(drift, n):
            atr[i] = (atr[i - 1] * (drift - 1) + tr[i]) / drift

    # Compute rolling sum of ATR over 'period'
    atr_sum = np.empty(n, dtype=np.float64)
    for i in range(n):
        atr_sum[i] = np.nan
    for i in range(period - 1, n):
        valid = True
        window_sum = 0.0
        for j in range(i - period + 1, i + 1):
            if np.isnan(atr[j]):
                valid = False
                break
            window_sum += atr[j]
        if valid:
            atr_sum[i] = window_sum
        else:
            atr_sum[i] = np.nan

    # Compute rolling maximum of high over 'period'
    hh = np.empty(n, dtype=np.float64)
    for i in range(n):
        hh[i] = np.nan
    for i in range(period - 1, n):
        max_val = -1e100  # very low number as initial max
        valid = True
        for j in range(i - period + 1, i + 1):
            if np.isnan(high[j]):
                valid = False
                break
            if high[j] > max_val:
                max_val = high[j]
        if valid:
            hh[i] = max_val
        else:
            hh[i] = np.nan

    # Compute rolling minimum of low over 'period'
    ll = np.empty(n, dtype=np.float64)
    for i in range(n):
        ll[i] = np.nan
    for i in range(period - 1, n):
        min_val = 1e100  # very high number as initial min
        valid = True
        for j in range(i - period + 1, i + 1):
            if np.isnan(low[j]):
                valid = False
                break
            if low[j] < min_val:
                min_val = low[j]
        if valid:
            ll[i] = min_val
        else:
            ll[i] = np.nan

    # Compute the Choppiness Index result
    res = np.empty(n, dtype=np.float64)
    for i in range(n):
        res[i] = np.nan
    log_period = np.log10(period)
    for i in range(period - 1, n):
        if np.isnan(atr_sum[i]) or np.isnan(hh[i]) or np.isnan(ll[i]) or (hh[i] - ll[i]) <= 0:
            res[i] = np.nan
        else:
            res[i] = (scalar * (np.log10(atr_sum[i]) - np.log10(hh[i] - ll[i]))) / log_period

    return res
