from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, same_length, slice_candles


@njit
def _nvi_fast(source: np.ndarray, volume: np.ndarray) -> np.ndarray:
    res = np.ones_like(source)
    res[0] = 1000  # Starting value (conventional)

    for i in range(1, len(source)):
        if volume[i] < volume[i-1]:
            res[i] = res[i-1] * (1 + ((source[i] - source[i-1]) / source[i-1]))
        else:
            res[i] = res[i-1]

    return res


def nvi(candles: np.ndarray, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    NVI - Negative Volume Index

    The Negative Volume Index (NVI) is a cumulative indicator that uses the change in volume to decide when to track the price of an asset. 
    It suggests that smart money is at work when volume decreases and vice versa.

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    res = _nvi_fast(source, candles[:, 5])

    return same_length(candles, res) if sequential else res[-1]
