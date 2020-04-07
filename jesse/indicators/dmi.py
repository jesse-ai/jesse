import numpy as np
import talib

from collections import namedtuple

DMI = namedtuple('DMI', ['plus', 'minus'])


def dmi(candles: np.ndarray, period=14, sequential=False) -> DMI:
    """
    DMI - Directional Movement Index

    :param candles: np.ndarray
    :param period: int - default=14
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    MINUS_DI  = talib.MINUS_DI(candles[:, 3], candles[:, 4], candles[:, 2], timeperiod=period)
    PLUS_DI  = talib.PLUS_DI(candles[:, 3], candles[:, 4], candles[:, 2], timeperiod=period)

    if sequential:
        return DMI(PLUS_DI, MINUS_DI)
    else:
        return DMI(PLUS_DI[-1], MINUS_DI[-1])
