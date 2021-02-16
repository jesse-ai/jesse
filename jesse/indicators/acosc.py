from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_config

AC = namedtuple('AC', ['osc', 'change'])


def acosc(candles: np.ndarray, sequential: bool = False) -> AC:
    """
    Acceleration / Deceleration Oscillator (AC)

    :param candles: np.ndarray
    :param sequential: bool - default=False

    :return: AC(osc, change)
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    med = talib.MEDPRICE(candles[:, 3], candles[:, 4])
    ao = talib.SMA(med, 5) - talib.SMA(med, 34)

    res = ao - talib.SMA(ao, 5)
    mom = talib.MOM(res, timeperiod=1)

    if sequential:
        return AC(res, mom)
    else:
        return AC(res[-1], mom[-1])
