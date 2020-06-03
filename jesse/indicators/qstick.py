from typing import Union

import numpy as np
import tulipy as ti


def qstick(candles: np.ndarray, period=5, sequential=False) -> Union[float, np.ndarray]:
    """
    Qstick

    :param candles: np.ndarray
    :param period: int - default: 5
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = ti.qstick(np.ascontiguousarray(candles[:, 1]), np.ascontiguousarray(candles[:, 2]), period=period)

    return np.concatenate((np.full((candles.shape[0] - res.shape[0]), np.nan), res), axis=0) if sequential else res[-1]
