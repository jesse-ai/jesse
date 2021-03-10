from collections import namedtuple

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, slice_candles

ITREND = namedtuple('ITREND', ['signal', 'it', 'trigger'])


def itrend(candles: np.ndarray, alpha: float = 0.07, source_type: str = "hl2", sequential: bool = False) -> ITREND:
    """
    Instantaneous Trendline

    :param candles: np.ndarray
    :param alpha: float - default: 0.07
    :param source_type: str - default: "hl2"
    :param sequential: bool - default=False

    :return: ITREND(signal, it, trigger)
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    signal, it, trigger = itrend_fast(source, alpha)

    if sequential:
        return ITREND(signal, it, trigger)
    else:
        return ITREND(signal[-1], it[-1], trigger[-1])


@njit
def itrend_fast(source, alpha):
    it = np.copy(source)
    for i in range(2, 7):
        it[i] = (source[i] + 2 * source[i - 1] + source[i - 2]) / 4
    for i in range(7, source.shape[0]):
        it[i] = (alpha - alpha ** 2 / 4) * source[i] \
                + alpha ** 2 / 2 * source[i - 1] \
                - (alpha - alpha ** 2 * 3 / 4) * source[i - 2] \
                + 2 * (1 - alpha) * it[i - 1] - (1 - alpha) ** 2 * it[i - 2]

    # compute lead 2 trigger & signal
    lag2 = np.roll(it, 20)
    lag2[:20] = it[:20]
    trigger = 2 * it - lag2
    signal = (trigger > it) * 1 - (trigger < it) * 1
    return signal, it, trigger
