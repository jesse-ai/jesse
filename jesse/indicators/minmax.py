import numpy as np
from scipy.signal import argrelextrema

from collections import namedtuple

EXTREMA = namedtuple('EXTREMA', ['min', 'max'])


def minmax(candles: np.ndarray, order=3, sequential=False) -> EXTREMA:
    """
    minmax

    :param candles: np.ndarray
    :param mode: int - default = 0
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    low = candles[:, 4]
    high = candles[:, 3]

    minimaIdxs = argrelextrema(low, np.less, order=order, axis=0)
    maximaIdxs = argrelextrema(high, np.greater, order=order, axis=0)

    min = np.full_like(low, np.nan)
    max = np.full_like(high, np.nan)

    min[minimaIdxs] = low[minimaIdxs]
    max[maximaIdxs] = high[maximaIdxs]

    if sequential:
        return EXTREMA(min, max)
    else:
        return EXTREMA(min[-1], max[-1])
