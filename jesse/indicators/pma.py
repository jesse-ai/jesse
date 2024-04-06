from collections import namedtuple

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, slice_candles

PMA = namedtuple('PMA', ['predict', 'trigger'])

def pma(candles: np.ndarray, source_type: str = "hl2", sequential: bool = False) -> PMA:
    """
    Ehlers Predictive Moving Average

    :param candles: np.ndarray
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

    predict, trigger = pma_fast(source)

    if sequential:
        return PMA(predict, trigger)
    else:
        return PMA(predict[-1], trigger[-1])


@njit(cache=True)
def pma_fast(source):
    predict = np.full_like(source, np.nan)
    trigger = np.full_like(source, np.nan)
    wma1 = np.zeros_like(source)
    for j in range(6, source.shape[0]):
        wma1[j] = ((7 * source[j]) + (6 * source[j -1]) + (5 * source[j -2]) + (4 * source[j -3]) + (3 * source[j -4]) + (2 * source[j -5]) + source[j -6]) / 28
        wma2 = ((7 * wma1[j]) + (6 * wma1[j-1]) + (5 * wma1[j -2]) + (4 * wma1[j -3]) + (3 * wma1[j -4]) + (2 * wma1[j -5]) + wma1[j -6]) / 28
        predict[j] = (2 * wma1[j]) - wma2
        trigger[j] = ((4 * predict[j]) + (3 * predict[j-1]) + (2 * predict[j -2]) + predict[j -3]) / 10
    return predict, trigger
