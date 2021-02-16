from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_config

AROON = namedtuple('AROON', ['down', 'up'])


def aroon(candles: np.ndarray, period: int = 14, sequential: bool = False) -> AROON:
    """
    AROON - Aroon

    :param candles: np.ndarray
    :param period: int - default=14
    :param sequential: bool - default=False

    :return: AROON(down, up)
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    aroondown, aroonup = talib.AROON(candles[:, 3], candles[:, 4], timeperiod=period)

    if sequential:
        return AROON(aroondown, aroonup)
    else:
        return AROON(aroondown[-1], aroonup[-1])
