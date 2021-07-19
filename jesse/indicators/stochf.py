from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import slice_candles
from jesse.indicators.ma import ma

StochasticFast = namedtuple('StochasticFast', ['k', 'd'])


def stochf(candles: np.ndarray, fastk_period: int = 5, fastd_period: int = 3, fastd_matype: int = 0,
           sequential: bool = False) -> StochasticFast:
    """
    Stochastic Fast

    :param candles: np.ndarray
    :param fastk_period: int - default: 5
    :param fastd_period: int - default: 3
    :param fastd_matype: int - default: 0
    :param sequential: bool - default: False

    :return: StochasticFast(k, d)
    """
    candles = slice_candles(candles, sequential)

    candles_close = candles[:, 2]
    candles_high = candles[:, 3]
    candles_low = candles[:, 4]

    hh = talib.MAX(candles_high, fastk_period)
    ll = talib.MIN(candles_low, fastk_period)

    k = 100 * (candles_close - ll) / (hh - ll)
    d = ma(k, period=fastd_period, matype=fastd_matype, sequential=True)

    if sequential:
        return StochasticFast(k, d)
    else:
        return StochasticFast(k[-1], d[-1])
