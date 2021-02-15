import math
from typing import Union

import numpy as np

from jesse.helpers import get_config
from .supersmoother import supersmoother


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

    warmup_candles_num = get_config('env.data.warmup_candles_num', 210)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    ssf = supersmoother(candles, cutoff=period / 2, source_type=source_type, sequential=True)

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
                tf[i] = sums[i] / math.sqrt(ms[i])

    if sequential:
        return tf
    else:
        return None if np.isnan(tf[-1]) else tf[-1]
