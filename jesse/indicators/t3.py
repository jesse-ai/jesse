import numpy as np
import talib

from typing import Union


def t3(candles: np.ndarray, period=5, vfactor=0, sequential=False) -> Union[float, np.ndarray]:
    """
    T3 - Triple Exponential Moving Average (T3)

    :param candles: np.ndarray
    :param period: int - default: 5
    :param vfactor: float - default: 0
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.T3(candles[:, 2], timeperiod=period, vfactor=vfactor)

    return res if sequential else res[-1]
