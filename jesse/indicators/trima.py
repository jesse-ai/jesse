import numpy as np
import talib

from typing import Union


def trima(candles: np.ndarray, period=30, sequential=False) -> Union[float, np.ndarray]:
    """
    TRIMA - Triangular Moving Average

    :param candles: np.ndarray
    :param period: int - default: 30
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.TRIMA(candles[:, 2], timeperiod=period)

    return res if sequential else res[-1]
