from typing import Union

import numpy as np
import talib


def typprice(candles: np.ndarray, sequential=False) -> Union[float, np.ndarray]:
    """
    TYPPRICE - Typical Price

    :param candles: np.ndarray
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.TYPPRICE(candles[:, 3], candles[:, 4], candles[:, 2])

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
