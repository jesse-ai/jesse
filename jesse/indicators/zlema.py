import numpy as np
import tulipy as ti
from typing import Union


def zlema(candles: np.ndarray, period=20, sequential=False) -> Union[float, np.ndarray]:
    """
    Zero-Lag Exponential Moving Average

    :param candles: np.ndarray
    :param period: int - default: 20
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = ti.zlema(np.ascontiguousarray(candles[:, 2]), period=period)

    return np.concatenate((np.full((candles.shape[0]-res.shape[0]), np.nan), res), axis=0) if sequential else res[-1]
