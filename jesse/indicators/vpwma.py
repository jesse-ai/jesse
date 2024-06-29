from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, slice_candles


def vpwma(candles: np.ndarray, period: int = 14, power: float = 0.382, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Variable Power Weighted Moving Average

    :param candles: np.ndarray
    :param period: int - default: 14
    :param power: float - default: 0.382
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """

    # Accept normal array too.
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    res = vpwma_fast(source, period, power)

    return res if sequential else res[-1]


@njit(cache=True)
def vpwma_fast(source, period, power):
    newseries = np.copy(source)
    for j in range(period + 1, source.shape[0]):
        my_sum = 0.0
        weightSum = 0.0
        for i in range(period - 1):
            weight = np.power(period - i, power)
            my_sum += (source[j - i] * weight)
            weightSum += weight
        newseries[j] = my_sum / weightSum
    return newseries
