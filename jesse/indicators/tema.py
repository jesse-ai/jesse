import numpy as np
import talib

from typing import Union


def tema(candles: np.ndarray, period=9, sequential=False) -> Union[float, np.ndarray]:
    """
    TEMA - Triple Exponential Moving Average

    :param candles: np.ndarray
    :param period: int - default: 9
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.TEMA(candles[:, 2], timeperiod=period)

    return res if sequential else res[-1]
