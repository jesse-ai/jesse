from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, same_length, slice_candles


@njit
def _pvi_fast(source: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """
    Numba optimized PVI calculation
    """
    pvi = np.zeros_like(source)
    pvi[0] = 1000  # Starting value

    for i in range(1, len(source)):
        if volume[i] > volume[i-1]:
            pvi[i] = pvi[i-1] * (1 + (source[i] - source[i-1]) / source[i-1])
        else:
            pvi[i] = pvi[i-1]

    return pvi


def pvi(candles: np.ndarray, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    PVI - Positive Volume Index

    The Positive Volume Index (PVI) focuses on days when volume increases from the previous day.
    The premise behind the PVI is that price changes accompanied by increased volume are more significant.

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    res = _pvi_fast(np.ascontiguousarray(source), np.ascontiguousarray(candles[:, 5]))

    return same_length(candles, res) if sequential else res[-1]
