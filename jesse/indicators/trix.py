import numpy as np
import talib

from typing import Union


def trix(candles: np.ndarray, period=18, sequential=False) -> Union[float, np.ndarray]:
    """
    TRIX - 1-day Rate-Of-Change (ROC) of a Triple Smooth EMA

    :param candles: np.ndarray
    :param period: int - default: 18
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    r = talib.TRIX(candles[:, 2], timeperiod=period) * 100

    return r if sequential else r[-1]
