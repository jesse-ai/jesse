from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import slice_candles

AROON = namedtuple('AROON', ['down', 'up'])


def aroon(candles: np.ndarray, period: int = 14, sequential: bool = False) -> AROON:
    """
    AROON - Aroon

    :param candles: np.ndarray
    :param period: int - default=14
    :param sequential: bool - default=False

    :return: AROON(down, up)
    """
    candles = slice_candles(candles, sequential)

    aroondown, aroonup = talib.AROON(candles[:, 3], candles[:, 4], timeperiod=period)

    if sequential:
        return AROON(aroondown, aroonup)
    else:
        return AROON(aroondown[-1], aroonup[-1])
