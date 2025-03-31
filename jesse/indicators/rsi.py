import numpy as np
from typing import Union
from numba import njit

from jesse.helpers import get_candle_source, slice_candles


@njit(cache=True)
def _rsi(p: np.ndarray, period: int) -> np.ndarray:
    """
    Compute the Relative Strength Index using a loop and Wilder's smoothing.
    """
    n = len(p)
    rsi_arr = np.full(n, np.nan)
    if n < period + 1:
        return rsi_arr
    # Calculate differences between consecutive prices.
    diff = np.empty(n - 1)
    for i in range(n - 1):
        diff[i] = p[i+1] - p[i]

    # Compute initial average gain and loss over the first 'period' differences.
    sum_gain = 0.0
    sum_loss = 0.0
    for i in range(period):
        change = diff[i]
        if change > 0:
            sum_gain += change
        else:
            sum_loss += -change
    avg_gain = sum_gain / period
    avg_loss = sum_loss / period

    # Compute first RSI value at index 'period'
    if avg_loss == 0:
        rsi_arr[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_arr[period] = 100 - (100 / (1 + rs))

    # Recursively update average gain and loss and compute subsequent RSI values.
    for i in range(period, n - 1):
        change = diff[i]
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            rsi_arr[i+1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_arr[i+1] = 100 - (100 / (1 + rs))
    return rsi_arr


def rsi(candles: np.ndarray, period: int = 14, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    RSI - Relative Strength Index using Numba for optimization

    :param candles: np.ndarray
    :param period: int - default: 14
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    p = np.asarray(source, dtype=float)
    result = _rsi(p, period)
    return result if sequential else result[-1]
