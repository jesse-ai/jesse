from collections import namedtuple

import numpy as np
import talib

Stochastic = namedtuple('Stochastic', ['k', 'd'])


def stoch(candles: np.ndarray, fastk_period=14, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0,
          sequential=False) -> Stochastic:
    """
    The Stochastic Oscillator

    :param candles: np.ndarray
    :param period: int - default=14
    :param sequential: bool - default=False

    :return: Stochastic(k, d)
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    k, d = talib.STOCH(
        candles[:, 3],
        candles[:, 4],
        candles[:, 2],
        fastk_period=fastk_period,
        slowk_period=slowk_period,
        slowk_matype=slowk_matype,
        slowd_period=slowd_period,
        slowd_matype=slowd_matype
    )

    if sequential:
        return Stochastic(k, d)
    else:
        return Stochastic(k[-1], d[-1])
