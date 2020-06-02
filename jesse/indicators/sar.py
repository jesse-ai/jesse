from typing import Union

import numpy as np
import talib


def sar(candles: np.ndarray, acceleration=0.02, maximum=0.2, sequential=False) -> Union[float, np.ndarray]:
    """
    SAR - Parabolic SAR

    :param candles: np.ndarray
    :param acceleration: float - default: 0.02
    :param maximum: float - default: 0.2
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.SAR(candles[:, 3], candles[:, 4], acceleration=acceleration, maximum=maximum)

    return res if sequential else res[-1]
