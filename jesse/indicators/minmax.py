from collections import namedtuple

import numpy as np
from scipy.signal import argrelextrema

from jesse.helpers import np_ffill, slice_candles

EXTREMA = namedtuple('EXTREMA', ['is_min', 'is_max', 'last_min', 'last_max'])


def minmax(candles: np.ndarray, order: int = 3, sequential: bool = False) -> EXTREMA:
    """
    minmax - Get extrema

    :param candles: np.ndarray
    :param order: int - default = 3
    :param sequential: bool - default: False

    :return: EXTREMA(min, max, last_min, last_max)
    """
    candles = slice_candles(candles, sequential)

    low = candles[:, 4]
    high = candles[:, 3]

    minimaIdxs = argrelextrema(low, np.less, order=order, axis=0)
    maximaIdxs = argrelextrema(high, np.greater, order=order, axis=0)

    is_min = np.full_like(low, np.nan)
    is_max = np.full_like(high, np.nan)

    # set the extremas with the matching price
    is_min[minimaIdxs] = low[minimaIdxs]
    is_max[maximaIdxs] = high[maximaIdxs]

    # forward fill Nan values to get the last extrema
    last_min = np_ffill(is_min)
    last_max = np_ffill(is_max)

    if sequential:
        return EXTREMA(is_min, is_max, last_min, last_max)
    else:
        return EXTREMA(is_min[-(order+1)], is_max[-(order+1)], last_min[-1], last_max[-1])
