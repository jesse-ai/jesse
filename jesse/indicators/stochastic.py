from collections import namedtuple

import numpy as np
import talib
from jesse.indicators.ma import ma

from jesse.helpers import slice_candles

Stochastic = namedtuple('Stochastic', ['k', 'd'])


def stoch(candles: np.ndarray, fastk_period: int = 14, slowk_period: int = 3, slowk_matype: int = 0,
          slowd_period: int = 3, slowd_matype: int = 0, sequential: bool = False) -> Stochastic:
    """
    The Stochastic Oscillator

    :param candles: np.ndarray
    :param fastk_period: int - default=14
    :param slowk_period: int - default=3
    :param slowk_matype: int - default=0
    :param slowd_period: int - default=3
    :param slowd_matype: int - default=0
    :param sequential: bool - default=False

    :return: Stochastic(k, d)
    """
    candles = slice_candles(candles, sequential)

    candles_close = candles[:, 2]
    candles_high = candles[:, 3]
    candles_low = candles[:, 4]

    hh = talib.MAX(candles_high, fastk_period)
    ll = talib.MIN(candles_low, fastk_period)

    stoch = 100 * (candles_close - ll) / (hh - ll)
    k = ma(stoch, period=slowk_period, matype=slowk_matype, sequential=True)
    d = ma(k, period=slowd_period, matype=slowd_matype, sequential=True)

    if sequential:
        return Stochastic(k, d)
    else:
        return Stochastic(k[-1], d[-1])
