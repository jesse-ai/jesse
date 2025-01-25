from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, same_length, slice_candles


@njit
def _zlema_fast(source: np.ndarray, period: int) -> np.ndarray:
    lag = (period - 1) / 2
    lag = int(lag)

    # Pre-allocate the output array
    res = np.zeros_like(source)

    # Calculate the smoothing factor
    alpha = 2 / (period + 1)

    # Calculate ema_data = price + (price - price_lag)
    ema_data = np.zeros_like(source)
    for i in range(lag, len(source)):
        ema_data[i] = source[i] + (source[i] - source[i - lag])

    # First value is a simple copy
    res[lag] = ema_data[lag]

    # Calculate ZLEMA
    for i in range(lag + 1, len(source)):
        res[i] = (alpha * ema_data[i]) + ((1 - alpha) * res[i - 1])

    return res


def zlema(candles: np.ndarray, period: int = 20, source_type: str = "close", sequential: bool = False) -> Union[
        float, np.ndarray]:
    """
    Zero-Lag Exponential Moving Average

    :param candles: np.ndarray
    :param period: int - default: 20
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    res = _zlema_fast(source, period)

    return same_length(candles, res) if sequential else res[-1]
