from collections import namedtuple

import numpy as np
import talib

StochasticFast = namedtuple('StochasticFast', ['k', 'd'])


def stochf(candles: np.ndarray, fastk_period=5, fastd_period=3, fastd_matype=0, sequential=False) -> StochasticFast:
    """
    Stochastic Fast

    :param candles: np.ndarray
    :param fastk_period: int - default=5
    :param fastd_period: int - default=3
    :param fastd_matype: int - default=0
    :param sequential: bool - default=False

    :return: StochasticFast(k, d)
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    k, d = talib.STOCHF(
        candles[:, 3],
        candles[:, 4],
        candles[:, 2],
        fastk_period=fastk_period,
        fastd_period=fastd_period,
        fastd_matype=fastd_matype
    )

    if sequential:
        return StochasticFast(k, d)
    else:
        return StochasticFast(k[-1], d[-1])
