from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source
from jesse.helpers import get_config
from .supersmoother import supersmoother_fast


def trendflex(candles: np.ndarray, period: int = 20, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Trendflex indicator by John F. Ehlers

    :param candles: np.ndarray
    :param period: int - default=20
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """

    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    source = get_candle_source(candles, source_type=source_type)

    ssf = supersmoother_fast(source, period / 2)

    tf = trendflex_fast(ssf, period)

    if sequential:
        return tf
    else:
        return None if np.isnan(tf[-1]) else tf[-1]


@njit
def trendflex_fast(ssf, period):
    tf = np.full_like(ssf, 0)
    ms = np.full_like(ssf, 0)
    sums = np.full_like(ssf, 0)

    for i in range(ssf.shape[0]):
        if not (i < period):
            sum = 0
            for t in range(1, period + 1):
                sum = sum + ssf[i] - ssf[i - t]
            sum = sum / period
            sums[i] = sum

            ms[i] = 0.04 * sums[i] * sums[i] + 0.96 * ms[i - 1]
            if ms[i] != 0:
                tf[i] = sums[i] / np.sqrt(ms[i])
    return tf
