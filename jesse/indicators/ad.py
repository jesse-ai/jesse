from typing import Union

import numpy as np
import talib


def ad(candles: np.ndarray, sequential=False) -> Union[float, np.ndarray]:
    """
    AD - Chaikin A/D Line

    :param candles: np.ndarray
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.AD(candles[:, 3], candles[:, 4], candles[:, 2], candles[:, 5])

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
