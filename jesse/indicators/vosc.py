from typing import Union

import numpy as np
import tulipy as ti


def vosc(candles: np.ndarray, short_period=2, long_period=5,  sequential=False) -> Union[float, np.ndarray]:
    """
    VOSC - Volume Oscillator

    :param candles: np.ndarray
    :param short_period: int - default: 2
    :param long_period: int - default: 5
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = ti.vosc(np.ascontiguousarray(candles[:, 5]), short_period=short_period, long_period=long_period)

    return np.concatenate((np.full((candles.shape[0] - res.shape[0]), np.nan), res), axis=0) if sequential else res[-1]
