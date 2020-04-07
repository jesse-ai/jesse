import numpy as np
import talib

from typing import Union


def ht_trendline(candles: np.ndarray, sequential=False) -> Union[float, np.ndarray]:
    """
    HT_TRENDLINE - Hilbert Transform - Instantaneous Trendline

    :param candles: np.ndarray
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.HT_TRENDLINE(candles[:, 2])

    return res if sequential else res[-1]
