from collections import namedtuple

import numpy as np
from numba import njit
from jesse.helpers import get_candle_source, slice_candles

MACD = namedtuple('MACD', ['macd', 'signal', 'hist'])

@njit
def ema_numba(source, period):
    ema_array = np.empty_like(source)
    alpha = 2.0 / (period + 1)
    ema_array[0] = source[0]
    for i in range(1, len(source)):
        ema_array[i] = alpha * source[i] + (1 - alpha) * ema_array[i - 1]
    return ema_array

@njit
def subtract_arrays(a, b):
    c = np.empty_like(a)
    for i in range(len(a)):
        c[i] = a[i] - b[i]
    return c

@njit
def clean_nan(arr):
    # Replace NaN with 0.0 using a simple loop (nan != nan is True)
    for i in range(arr.shape[0]):
        if arr[i] != arr[i]:
            arr[i] = 0.0
    return arr


def macd(candles: np.ndarray, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9,
         source_type: str = "close",
         sequential: bool = False) -> MACD:
    """
    MACD - Moving Average Convergence/Divergence using numba for faster computation

    :param candles: np.ndarray
    :param fast_period: int - default: 12
    :param slow_period: int - default: 26
    :param signal_period: int - default: 9
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: MACD(macd, signal, hist)
    """

    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    # Compute fast and slow EMAs using numba accelerated function
    ema_fast = ema_numba(source, fast_period)
    ema_slow = ema_numba(source, slow_period)

    # Compute the MACD line using a numba-compiled subtraction loop
    macd_line = subtract_arrays(ema_fast, ema_slow)
    macd_line_cleaned = clean_nan(macd_line)

    # Compute the signal line as the EMA of the MACD line
    signal_line = ema_numba(macd_line_cleaned, signal_period)
    
    # Calculate histogram as the difference between MACD line and signal line
    hist = subtract_arrays(macd_line, signal_line)

    if sequential:
        return MACD(macd_line_cleaned, signal_line, hist)
    else:
        return MACD(macd_line_cleaned[-1], signal_line[-1], hist[-1])
