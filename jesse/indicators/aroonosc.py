from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import slice_candles

@njit(cache=True)
def _compute_aroonosc_nb(high: np.ndarray, low: np.ndarray, period: int) -> np.ndarray:
    n = high.shape[0]
    result = np.empty(n, dtype=np.float64)
    if n < period:
        for i in range(n):
            result[i] = np.nan
        return result
    
    for i in range(period - 1):
        result[i] = np.nan
    
    for i in range(period - 1, n):
        start = i - period + 1
        best_val = high[start]
        best_idx = 0
        worst_val = low[start]
        worst_idx = 0
        for j in range(period):
            cur_high = high[start + j]
            cur_low = low[start + j]
            if cur_high > best_val:
                best_val = cur_high
                best_idx = j
            if cur_low < worst_val:
                worst_val = cur_low
                worst_idx = j
        result[i] = 100.0 * (best_idx - worst_idx) / period
    return result


def aroonosc(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    AROONOSC - Aroon Oscillator

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    high = candles[:, 3]
    low = candles[:, 4]
    result = _compute_aroonosc_nb(high, low, period)
    return result if sequential else result[-1]
