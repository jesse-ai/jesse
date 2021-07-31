from typing import Union

import numpy as np
try:
    from numba import njit
except ImportError:
    njit = lambda a : a

from jesse.helpers import get_candle_source, slice_candles
from .supersmoother import supersmoother_fast


def reflex(candles: np.ndarray, period: int = 20, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Reflex indicator by John F. Ehlers

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


    ssf = supersmoother_fast(source, period / 2)
    rf = reflex_fast(ssf, period)

    if sequential:
        return rf
    else:
        return None if np.isnan(rf[-1]) else rf[-1]


@njit
def reflex_fast(ssf, period):
    rf = np.full_like(ssf, 0)
    ms = np.full_like(ssf, 0)
    sums = np.full_like(ssf, 0)
    for i in range(ssf.shape[0]):
        if i >= period:
            slope = (ssf[i - period] - ssf[i]) / period
            my_sum = 0
            for t in range(1, period + 1):
                my_sum = my_sum + (ssf[i] + t * slope) - ssf[i - t]
            my_sum /= period
            sums[i] = my_sum

            ms[i] = 0.04 * sums[i] * sums[i] + 0.96 * ms[i - 1]
            if ms[i] > 0:
                rf[i] = sums[i] / np.sqrt(ms[i])
    return rf
