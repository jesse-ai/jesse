from collections import namedtuple

import numpy as np
import talib

AC = namedtuple('AC', ['osc', 'change'])


def acosc(candles: np.ndarray, sequential=False) -> AC:
    """
    Acceleration / Deceleration Oscillator (AC)

    :param candles: np.ndarray
    :param sequential: bool - default=False

    :return: AC(osc, change)
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    med = talib.MEDPRICE(candles[:, 3], candles[:, 4])
    ao = talib.SMA(med, 5) - talib.SMA(med, 34)

    res = ao - talib.SMA(ao, 5)
    mom = talib.MOM(res, timeperiod=1)

    if sequential:
        return AC(res, mom)
    else:
        return AC(res[-1], mom[-1])
