from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import slice_candles

DonchianChannel = namedtuple('DonchianChannel', ['upperband', 'middleband', 'lowerband'])


def donchian(candles: np.ndarray, period: int = 20, sequential: bool = False) -> DonchianChannel:
    """
    Donchian Channels

    :param candles: np.ndarray
    :param period: int - default: 20
    :param sequential: bool - default=False

    :return: DonchianChannel(upperband, middleband, lowerband)
    """
    candles = slice_candles(candles, sequential)

    UC = talib.MAX(candles[:, 3], timeperiod=period)
    LC = talib.MIN(candles[:, 4], timeperiod=period)
    MC = ((UC + LC) / 2)

    if sequential:
        return DonchianChannel(UC, MC, LC)
    else:
        return DonchianChannel(UC[-1], MC[-1], LC[-1])
