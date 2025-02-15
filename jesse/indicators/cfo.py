from typing import Union
import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, slice_candles

@njit(cache=True)
def _compute_cfo(source: np.ndarray, period: int, scalar: float) -> np.ndarray:
    n = source.shape[0]
    res = np.empty(n, dtype=np.float64)
    # fill initial values with nan for indices where a full period is not available
    for i in range(period - 1):
        res[i] = np.nan

    # Precompute constants for x = 0, 1, ..., period-1
    Sx = 0.0
    Sxx = 0.0
    for j in range(period):
        Sx += j
        Sxx += j * j
    denom = period * Sxx - Sx * Sx

    # For each valid window, compute the linear regression and forecast value
    for i in range(period - 1, n):
        sum_y = 0.0
        sum_xy = 0.0
        for j in range(period):
            y_val = source[i - period + 1 + j]
            sum_y += y_val
            sum_xy += y_val * j
        slope = (period * sum_xy - Sx * sum_y) / denom
        intercept = (sum_y - slope * Sx) / period
        reg_val = intercept + slope * (period - 1)
        # Avoid division by zero
        if source[i] != 0.0:
            res[i] = scalar * (source[i] - reg_val) / source[i]
        else:
            res[i] = np.nan
    return res


def cfo(candles: np.ndarray, period: int = 14, scalar: float = 100, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    CFO - Chande Forcast Oscillator

    :param candles: np.ndarray
    :param period: int - default: 14
    :param scalar: float - default: 100
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)

    res = _compute_cfo(source, period, scalar)
    
    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
