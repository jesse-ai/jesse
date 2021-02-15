from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source
from jesse.helpers import get_config


def supersmoother_3_pole(candles: np.ndarray, period: int = 14, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Super Smoother Filter 3pole Butterworth
    This indicator was described by John F. Ehlers

    :param candles: np.ndarray
    :param period: int - default=14
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """

    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    # Accept normal array too.
    if len(candles.shape) == 1:
        source = candles
    else:
        source = get_candle_source(candles, source_type=source_type)

    res = supersmoother_fast(source, period)

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]

@njit
def supersmoother_fast(source, period):
    a = np.exp(-np.pi / period)
    b = 2 * a * np.cos(1.738 * np.pi / period)
    c = a ** 2
    newseries = np.copy(source)
    for i in range(3, source.shape[0]):
        newseries[i] = (1 - c ** 2 - b + b * c) * source[i] \
                       + (b + c) * newseries[i - 1] + (-c - b * c) * newseries[i - 2] + (c ** 2) * newseries[i - 3]
    return newseries