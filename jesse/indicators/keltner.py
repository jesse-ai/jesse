from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_candle_source

KeltnerChannel = namedtuple('KeltnerChannel', ['upperband', 'middleband', 'lowerband'])


def keltner(candles: np.ndarray, period=20, multiplier=2, matype=1, source_type="close", sequential=False) -> KeltnerChannel:
    """
    Keltner Channels

    :param candles: np.ndarray
    :param period: int - default: 20
    :param multiplier: int - default: 2
    :param matype: int - default: 1
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: KeltnerChannel(upperband, middleband, lowerband)
    """

    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    e = talib.MA(source, timeperiod=period, matype=matype)
    a = talib.ATR(candles[:, 3], candles[:, 4], candles[:, 2], timeperiod=period)

    up = e + a * multiplier
    mid = e
    low = e - a * multiplier

    if sequential:
        return KeltnerChannel(up, mid, low)
    else:
        return KeltnerChannel(up[-1], mid[-1], low[-1])
