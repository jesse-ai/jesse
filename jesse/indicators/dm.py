from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import slice_candles

DM = namedtuple('DM', ['plus', 'minus'])


def dm(candles: np.ndarray, period: int = 14, sequential: bool = False) -> DM:
    """
    DM - Directional Movement

    :param candles: np.ndarray
    :param period: int - default=14
    :param sequential: bool - default=False

    :return: DM(plus, minus)
    """
    candles = slice_candles(candles, sequential)

    MINUS_DI = talib.MINUS_DM(candles[:, 3], candles[:, 4], timeperiod=period)
    PLUS_DI = talib.PLUS_DM(candles[:, 3], candles[:, 4], timeperiod=period)

    if sequential:
        return DM(PLUS_DI, MINUS_DI)
    else:
        return DM(PLUS_DI[-1], MINUS_DI[-1])
