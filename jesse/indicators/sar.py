from typing import Union

import numpy as np
import talib

from jesse.helpers import slice_candles


def sar(candles: np.ndarray, acceleration: float = 0.02, maximum: float = 0.2, sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    SAR - Parabolic SAR

    :param candles: np.ndarray
    :param acceleration: float - default: 0.02
    :param maximum: float - default: 0.2
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    res = talib.SAR(candles[:, 3], candles[:, 4], acceleration=acceleration, maximum=maximum)

    return res if sequential else res[-1]
