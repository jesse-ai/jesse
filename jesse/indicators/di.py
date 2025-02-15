from collections import namedtuple

import numpy as np

from jesse.helpers import slice_candles

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

    # Extract high, low, and close assuming columns: index 3 -> high, index 4 -> low, index 2 -> close
    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]

    # Calculate directional movements
    up_move = high[1:] - high[:-1]
    down_move = low[:-1] - low[1:]
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    # Calculate True Range (TR)
    high_low = high[1:] - low[1:]
    high_close = np.abs(high[1:] - close[:-1])
    low_close = np.abs(low[1:] - close[:-1])
    tr = np.maximum.reduce([high_low, high_close, low_close])

    m = len(tr)  # m = n - 1
    # Initialize arrays for Wilder's smoothing
    atr = np.full(m, np.nan)
    plus_smoothed = np.full(m, np.nan)
    minus_smoothed = np.full(m, np.nan)

    if m < period:
        plus_DI_arr = np.full(n, np.nan)
        minus_DI_arr = np.full(n, np.nan)
        if sequential:
            return DI(plus_DI_arr, minus_DI_arr)
        else:
            return DI(np.nan, np.nan)

    # Initial Wilder's smoothing
    atr[period - 1] = np.sum(tr[:period]) / period
    plus_smoothed[period - 1] = np.sum(plus_dm[:period])
    minus_smoothed[period - 1] = np.sum(minus_dm[:period])

    # Wilder's smoothing recursion
    for i in range(period, m):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
        plus_smoothed[i] = (plus_smoothed[i - 1] * (period - 1) + plus_dm[i]) / period
        minus_smoothed[i] = (minus_smoothed[i - 1] * (period - 1) + minus_dm[i]) / period

    # Prepare DI arrays: first 'period' candles are not computed (set to NaN)
    plus_DI_arr = np.full(n, np.nan)
    minus_DI_arr = np.full(n, np.nan)
    valid_indices = np.arange(period, n)
    plus_DI_arr[valid_indices] = np.where(atr[valid_indices - 1] == 0, 0, 100 * plus_smoothed[valid_indices - 1] / atr[valid_indices - 1])
    minus_DI_arr[valid_indices] = np.where(atr[valid_indices - 1] == 0, 0, 100 * minus_smoothed[valid_indices - 1] / atr[valid_indices - 1])

    if sequential:
        return DI(plus_DI_arr, minus_DI_arr)
    else:
        return DI(plus_DI_arr[-1], minus_DI_arr[-1])
