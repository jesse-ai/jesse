from collections import namedtuple

import numpy as np
import talib

DM = namedtuple('DM', ['plus', 'minus'])


def dm(candles: np.ndarray, period=14, sequential=False) -> DM:
    """
    DM - Directional Movement

    :param candles: np.ndarray
    :param period: int - default=14
    :param sequential: bool - default=False

    :return: DM(plus, minus)
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    MINUS_DI = talib.MINUS_DM(candles[:, 3], candles[:, 4],  timeperiod=period)
    PLUS_DI = talib.PLUS_DM(candles[:, 3], candles[:, 4],  timeperiod=period)

    if sequential:
        return DM(PLUS_DI, MINUS_DI)
    else:
        return DM(PLUS_DI[-1], MINUS_DI[-1])
