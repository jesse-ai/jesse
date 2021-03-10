from typing import Union

import numpy as np
import tulipy as ti

from jesse.helpers import slice_candles, same_length


def qstick(candles: np.ndarray, period: int = 5, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    Qstick

    :param candles: np.ndarray
    :param period: int - default: 5
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    res = ti.qstick(np.ascontiguousarray(candles[:, 1]), np.ascontiguousarray(candles[:, 2]), period=period)

    return same_length(candles, res) if sequential else res[-1]
