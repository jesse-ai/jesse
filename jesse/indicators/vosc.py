from typing import Union

import numpy as np
import tulipy as ti

from jesse.helpers import slice_candles, same_length


def vosc(candles: np.ndarray, short_period: int = 2, long_period: int = 5, sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    VOSC - Volume Oscillator

    :param candles: np.ndarray
    :param short_period: int - default: 2
    :param long_period: int - default: 5
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    res = ti.vosc(np.ascontiguousarray(candles[:, 5]), short_period=short_period, long_period=long_period)

    return same_length(candles, res) if sequential else res[-1]
