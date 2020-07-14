from collections import namedtuple

import numpy as np
from scipy.signal import argrelextrema

EXTREMA = namedtuple('EXTREMA', ['min', 'max', 'last_min', 'last_max'])


def minmax(candles: np.ndarray, order=3, sequential=False) -> EXTREMA:
    """
    minmax - Get extrema

    :param candles: np.ndarray
    :param order: int - default = 3
    :param sequential: bool - default=False

    :return: EXTREMA(min, max, last_min, last_max)
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    low = candles[:, 4]
    high = candles[:, 3]

    minimaIdxs = argrelextrema(low, np.less, order=order, axis=0)
    maximaIdxs = argrelextrema(high, np.greater, order=order, axis=0)

    min = np.full_like(low, np.nan)
    max = np.full_like(high, np.nan)

    # set the extremas with the matching price
    min[minimaIdxs] = low[minimaIdxs]
    max[maximaIdxs] = high[maximaIdxs]

    # forward fill Nan values to get the last extrema
    last_min = np_ffill(min)
    last_max = np_ffill(max)

    if sequential:
        return EXTREMA(min, max, last_min, last_max)
    else:
        return EXTREMA(min[-1], max[-1], last_min[-1], last_max[-1])


def np_ffill(arr, axis=0):
    """

    :param arr:
    :param axis:
    :return:
    """
    idx_shape = tuple([slice(None)] + [np.newaxis] * (len(arr.shape) - axis - 1))
    idx = np.where(~np.isnan(arr), np.arange(arr.shape[axis])[idx_shape], 0)
    np.maximum.accumulate(idx, axis=axis, out=idx)
    slc = [np.arange(k)[tuple([slice(None) if dim == i else np.newaxis
                               for dim in range(len(arr.shape))])]
           for i, k in enumerate(arr.shape)]
    slc[axis] = idx
    return arr[tuple(slc)]
