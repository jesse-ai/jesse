from collections import namedtuple

import numpy as np

from jesse.helpers import get_candle_source

ITREND = namedtuple('ITREND', ['signal', 'it', 'trigger'])


def itrend(candles: np.ndarray, alpha=0.07, source_type="hl2", sequential=False) -> ITREND:
    """
    Instantaneous Trendline

    :param candles: np.ndarray
    :param alpha: float - default: 0.07
    :param source_type: str - default: "hl2"
    :param sequential: bool - default=False

    :return: ITREND(signal, it, trigger)
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)

    coeff = np.array(
        [(alpha - alpha ** 2 / 4), alpha ** 2 / 2, - (alpha - alpha ** 2 * 3 / 4), 2 * (1 - alpha), - (1 - alpha) ** 2])

    it = np.copy(source)
    for i in range(2, 7):
        it[i] = (source[i] + 2 * source[i - 1] + source[i - 2]) / 4
    for i in range(7, source.shape[0]):
        val = np.array([source[i], source[i - 1], source[i - 2], it[i - 1], it[i - 2]])
        it[i] = np.matmul(coeff, val)

    # compute lead 2 trigger & signal
    lag2 = np.roll(it, 20)
    lag2[:20] = it[:20]
    trigger = 2 * it - lag2
    signal = (trigger > it) * 1 - (trigger < it) * 1

    if sequential:
        return ITREND(signal, it, trigger)
    else:
        return ITREND(signal[-1], it[-1], trigger[-1])
