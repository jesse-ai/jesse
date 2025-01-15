from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, same_length, slice_candles


@njit
def _wilders_fast(source: np.ndarray, period: int) -> np.ndarray:
    # Pre-allocate the output array
    res = np.zeros_like(source)
    # First value is a simple copy
    res[0] = source[0]

    # Calculate Wilder's Smoothing
    for i in range(1, len(source)):
        res[i] = (res[i - 1] * (period - 1) + source[i]) / period

    return res


def wilders(candles: np.ndarray, period: int = 5, source_type: str = "close", sequential: bool = False) -> Union[
        float, np.ndarray]:
    """
    WILDERS - Wilders Smoothing

    :param candles: np.ndarray
    :param period: int - default: 5
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    res = _wilders_fast(source, period)

    return same_length(candles, res) if sequential else res[-1]
