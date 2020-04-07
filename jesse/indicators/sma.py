import numpy as np
import talib

from typing import Union


def sma(candles: np.ndarray, period=5, sequential=False) -> Union[float, np.ndarray]:
    """
    SMA - Simple Moving Average

    :param candles: np.ndarray
    :param period: int - default: 5
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.SMA(candles[:, 2], timeperiod=period)

    return res if sequential else res[-1]
