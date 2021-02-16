from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_config

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
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

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
