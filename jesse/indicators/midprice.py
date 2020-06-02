from typing import Union

import numpy as np
import talib


def midprice(candles: np.ndarray, period=14, sequential=False) -> Union[float, np.ndarray]:
    """
    MIDPRICE - Midpoint Price over period

    :param candles: np.ndarray
    :param period: int - default=14
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.MIDPRICE(candles[:, 3], candles[:, 4], timeperiod=period)

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
