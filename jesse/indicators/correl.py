from typing import Union

import numpy as np
import talib


def correl(candles: np.ndarray, period=5, sequential=False) -> Union[float, np.ndarray]:
    """
    CORREL - Pearson's Correlation Coefficient (r)

    :param candles: np.ndarray
    :param period: int - default: 5
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.CORREL(candles[:, 3], candles[:, 4], timeperiod=period)

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
