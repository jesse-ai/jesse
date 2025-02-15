from typing import Union

import numpy as np
from numba import njit
from jesse.helpers import np_shift, slice_candles

@njit(cache=True)
def wilder_smoothing_numba(raw: np.ndarray, period: int) -> np.ndarray:
    smoothed = np.zeros_like(raw)
    alpha = 1 - 1/period
    smoothed[0] = raw[0]
    for i in range(1, len(raw)):
        smoothed[i] = alpha * smoothed[i-1] + raw[i]
    return smoothed

@njit(cache=True)
def rolling_max_numba(arr: np.ndarray, window: int) -> np.ndarray:
    n = len(arr)
    result = np.empty_like(arr)
    
    # Handle first window-1 elements
    for i in range(window-1):
        result[i] = np.max(arr[:i+1])
    
    # Handle remaining elements with sliding window
    for i in range(window-1, n):
        result[i] = np.max(arr[i-window+1:i+1])
    
    return result

@njit(cache=True)
def rolling_min_numba(arr: np.ndarray, window: int) -> np.ndarray:
    n = len(arr)
    result = np.empty_like(arr)
    
    # Handle first window-1 elements
    for i in range(window-1):
        result[i] = np.min(arr[:i+1])
    
    # Handle remaining elements with sliding window
    for i in range(window-1, n):
        result[i] = np.min(arr[i-window+1:i+1])
    
    return result

def safezonestop(candles: np.ndarray, period: int = 22, mult: float = 2.5, max_lookback: int = 3,
                 direction: str = "long", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    Safezone Stops - Numba optimized version

    :param candles: np.ndarray
    :param period: int - default: 22
    :param mult: float - default: 2.5
    :param max_lookback: int - default: 3
    :param direction: str - default: long
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    high = candles[:, 3]
    low = candles[:, 4]

    last_high = np_shift(high, 1, fill_value=np.nan)
    last_low = np_shift(low, 1, fill_value=np.nan)

    diff_high = high - last_high
    diff_low = last_low - low
    diff_high = np.where(np.isnan(diff_high), 0, diff_high)
    diff_low = np.where(np.isnan(diff_low), 0, diff_low)

    raw_plus_dm = np.where((diff_high > diff_low) & (diff_high > 0), diff_high, 0)
    raw_minus_dm = np.where((diff_low > diff_high) & (diff_low > 0), diff_low, 0)

    plus_dm = wilder_smoothing_numba(raw_plus_dm, period)
    minus_dm = wilder_smoothing_numba(raw_minus_dm, period)

    if direction == "long":
        intermediate = last_low - mult * minus_dm
        res = rolling_max_numba(intermediate, max_lookback)
    else:
        intermediate = last_high + mult * plus_dm
        res = rolling_min_numba(intermediate, max_lookback)

    return res if sequential else res[-1]
