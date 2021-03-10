from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import slice_candles

AO = namedtuple('AO', ['osc', 'change'])


def ao(candles: np.ndarray, sequential: bool = False) -> AO:
    """
    Awesome Oscillator

    :param candles: np.ndarray
    :param sequential: bool - default=False

    :return: AO(osc, change)
    """
    candles = slice_candles(candles, sequential)

    med = talib.MEDPRICE(candles[:, 3], candles[:, 4])
    res = talib.SMA(med, 5) - talib.SMA(med, 34)

    mom = talib.MOM(res, timeperiod=1)

    if sequential:
        return AO(res, mom)
    else:
        return AO(res[-1], mom[-1])
