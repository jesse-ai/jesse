from typing import Union

import numpy as np
import tulipy as ti

from jesse.helpers import same_length, slice_candles


def cvi(candles: np.ndarray, period: int = 5, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    CVI - Chaikins Volatility

    :param candles: np.ndarray
    :param period: int - default: 5
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    res = ti.cvi(np.ascontiguousarray(candles[:, 3]), np.ascontiguousarray(candles[:, 4]), period=period)

    return same_length(candles, res) if sequential else res[-1]
