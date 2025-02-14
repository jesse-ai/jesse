from typing import Union
import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, slice_candles

@njit(cache=True)
def _cmo_numba(source: np.ndarray, period: int) -> np.ndarray:
    n = source.shape[0]
    result = np.empty(n, dtype=np.float64)
    # Initialize result with NaN values
    for i in range(n):
        result[i] = np.nan
    
    if n <= 1:
        return result
    
    # Compute the differences manually
    diff = np.empty(n - 1, dtype=np.float64)
    for i in range(n - 1):
        diff[i] = source[i + 1] - source[i]
    
    # Only compute CMO if we have enough diff values
    if diff.shape[0] >= period:
        for i in range(period, n):
            pos_sum = 0.0
            neg_sum = 0.0
            # Calculate sums over the window diff[i-period:i]
            for j in range(i - period, i):
                d = diff[j]
                if d > 0:
                    pos_sum += d
                elif d < 0:
                    neg_sum += -d
            denom = pos_sum + neg_sum
            if denom == 0.0:
                result[i] = 0.0
            else:
                result[i] = 100.0 * (pos_sum - neg_sum) / denom
    return result


def cmo(candles: np.ndarray, period: int = 14, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    CMO - Chande Momentum Oscillator

    :param candles: np.ndarray
    :param period: int - default: 14
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    result = _cmo_numba(source, period)
    return result if sequential else result[-1]
