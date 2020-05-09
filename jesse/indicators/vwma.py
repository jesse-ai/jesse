import numpy as np
import tulipy as ti
from typing import Union


def vwma(candles: np.ndarray, period=20, sequential=False) -> Union[float, np.ndarray]:
    """
    VWMA - Volume Weighted Moving Average

    :param candles: np.ndarray
    :param period: int - default: 20
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = ti.vwma(np.ascontiguousarray(candles[:, 2]), np.ascontiguousarray(candles[:, 5]), period=period)

    return np.concatenate((np.full((period - 1), np.nan), res), axis=0) if sequential else res[-1]
