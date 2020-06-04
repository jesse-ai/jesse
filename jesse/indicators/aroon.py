from collections import namedtuple

import numpy as np
import talib

AROON = namedtuple('AROON', ['down', 'up'])


def aroon(candles: np.ndarray, period=14, sequential=False) -> AROON:
    """
    AROON - Aroon

    :param candles: np.ndarray
    :param period: int - default=14
    :param sequential: bool - default=False

    :return: AROON(down, up)
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    aroondown, aroonup = talib.AROON(candles[:, 3], candles[:, 4], timeperiod=period)

    if sequential:
        return AROON(aroondown, aroonup)
    else:
        return AROON(aroondown[-1], aroonup[-1])
