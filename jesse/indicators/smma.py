import numpy as np
import talib

from typing import Union


def smma(candles: np.ndarray, period=5, sequential=False) -> Union[float, np.ndarray]:
    """
    SMMA - Smoothed Moving Average

    :param candles: np.ndarray
    :param period: int - default: 5
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    # calculate the smoothed moving average
    res = numpy_ewma(candles[:, 2], period)

    return res if sequential else res[-1]


def numpy_ewma(data, window):
    alpha = 1 / window
    scale = 1/(1-alpha)
    n = data.shape[0]
    scale_arr = (1-alpha)**(-1*np.arange(n))
    weights = (1-alpha)**np.arange(n)
    pw0 = (1-alpha)**(n-1)
    mult = data*pw0*scale_arr
    cumsums = mult.cumsum()
    out = cumsums*scale_arr[::-1] / weights.cumsum()

    return out