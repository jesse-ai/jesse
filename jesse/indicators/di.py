from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_config

DI = namedtuple('DI', ['plus', 'minus'])


def di(candles: np.ndarray, period: int = 14, sequential: bool = False) -> DI:
    """
    DI - Directional Indicator

    :param candles: np.ndarray
    :param period: int - default=14
    :param sequential: bool - default=False

    :return: DI(plus, minus)
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    MINUS_DI = talib.MINUS_DI(candles[:, 3], candles[:, 4], candles[:, 2], timeperiod=period)
    PLUS_DI = talib.PLUS_DI(candles[:, 3], candles[:, 4], candles[:, 2], timeperiod=period)

    if sequential:
        return DI(PLUS_DI, MINUS_DI)
    else:
        return DI(PLUS_DI[-1], MINUS_DI[-1])
