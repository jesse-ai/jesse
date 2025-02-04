from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import slice_candles

AC = namedtuple('AC', ['osc', 'change'])


def acosc(candles: np.ndarray, sequential: bool = False) -> AC:
    """
    Acceleration / Deceleration Oscillator (AC)

    :param candles: np.ndarray
    :param sequential: bool - default: False

    :return: AC(osc, change)
    """
    candles = slice_candles(candles, sequential)

    med = talib.MEDPRICE(candles[:, 3], candles[:, 4])
    ao = talib.SMA(med, 5) - talib.SMA(med, 34)

    res = ao - talib.SMA(ao, 5)
    mom = talib.MOM(res, timeperiod=1)

    if sequential:
        return AC(res, mom)
    else:
        return AC(res[-1], mom[-1])
