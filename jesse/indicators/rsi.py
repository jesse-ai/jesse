import numpy as np
import talib

from typing import Union


def rsi(candles: np.ndarray, period=14, sequential=False) -> Union[float, np.ndarray]:
    """
    RSI - Relative Strength Index

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    r = talib.RSI(candles[:, 2], timeperiod=period)

    return r if sequential else r[-1]
