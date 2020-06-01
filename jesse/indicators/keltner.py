import numpy as np
import talib

from collections import namedtuple

from .ema import ema
from .atr import atr

KeltnerChannel = namedtuple('KeltnerChannel', ['upperband', 'middleband', 'lowerband'])

def keltner(candles: np.ndarray, period=20, multiplier=2, sequential=False) -> KeltnerChannel:
    """
    Keltner Channels

    :param candles: np.ndarray
    :param period: int - default: 20
    :param multiplier: int - default: 2
    :param sequential: bool - default=False

    :return: KeltnerChannel
    """

    e = ema(candles, period=period, sequential=sequential)
    a = atr(candles, period=period, sequential=sequential)

    if sequential:
        multiplier = a * 2
        return KeltnerChannel(e + multiplier, e, e - multiplier)
    else:
        multiplier = a * 2
        return KeltnerChannel(e + multiplier, e, e - multiplier)

