import numpy as np
import talib

from typing import Union


def ema(candles: np.ndarray, period=5, price="close", sequential=False) -> Union[float, np.ndarray]:
    """
    EMA - Exponential Moving Average

    :param candles: np.ndarray
    :param period: int - default: 5
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]
    if price == "open":
        res = talib.EMA(candles[:, 1], timeperiod=period)
    if price == "close":
        res = talib.EMA(candles[:, 2], timeperiod=period)
    if price == "high":
        res = talib.EMA(candles[:, 3], timeperiod=period)
    if price == "low":
        res = talib.EMA(candles[:, 4], timeperiod=period)
    return res if sequential else res[-1]
