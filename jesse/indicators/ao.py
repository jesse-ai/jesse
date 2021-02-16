from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_config

AO = namedtuple('AO', ['osc', 'change'])


def ao(candles: np.ndarray, sequential: bool = False) -> AO:
    """
    Awesome Oscillator

    :param candles: np.ndarray
    :param sequential: bool - default=False

    :return: AO(osc, change)
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    med = talib.MEDPRICE(candles[:, 3], candles[:, 4])
    res = talib.SMA(med, 5) - talib.SMA(med, 34)

    mom = talib.MOM(res, timeperiod=1)

    if sequential:
        return AO(res, mom)
    else:
        return AO(res[-1], mom[-1])
