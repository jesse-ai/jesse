from typing import Union

import numpy as np

from jesse.helpers import get_candle_source


def fractaldimension(candles: np.ndarray, window= 10, source_type="close", sequential=False) -> Union[float, np.ndarray]:
    """
    Fractal dimension

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """

    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)

    if window % 2 == 0:
        period1 = int(max(1, window / 2))
        period2 = int(max(1, window - period1))
        max_first, max_second = fractal_d_helper_max(source, window)
        min_first, min_second = fractal_d_helper_min(source, window)

        N1 = (max_first - min_first) / period1
        N2 = (max_second - min_second) / period2
        N3 = (maxval(source, window) - minval(source, window)) / window
        nu = N1 + N2
        nu[nu <= 0] = 1
        N3[N3 <= 0] = 1
        fractal = (np.log(N1 + N2) - np.log(N3)) / np.log(2)
    else:
        raise ValueError('Time Period for fractional dimension should be an even number')

    if sequential:
        return fractal
    else:
        return fractal[-1]


def fractal_d_helper_max(source, window):
    first = np.full_like(source, np.nan)
    second = np.full_like(source, np.nan)
    br = int(max(1, window / 2))
    strides = np.squeeze(rolling_window(source, (window, source.shape[1])))
    first_half = strides[:, :br, :]
    second_half = strides[:, br:, :]
    first[window - 1:, :] = first_half.max(axis=1)
    second[window - 1:, :] = second_half.max(axis=1)
    return first, second


def fractal_d_helper_min(source, window):
    first = np.full_like(source, np.nan)
    second = np.full_like(source, np.nan)
    br = int(max(1, window / 2))
    strides = np.squeeze(rolling_window(source, (window, source.shape[1])))
    first_half = strides[:, :br, :]
    second_half = strides[:, br:, :]
    first[window - 1:, :] = first_half.min(axis=1)
    second[window - 1:, :] = second_half.min(axis=1)
    return first, second

def rolling_window(source, shape):  # rolling window for 2D array
    s = (source.shape[0] - shape[0] + 1,) + (source.shape[1] - shape[1] + 1,) + shape
    strides = source.strides + source.strides
    return np.lib.stride_tricks.as_strided(source, shape=s, strides=strides)

def maxval(source,window):
    z = np.full_like(source,np.nan)
    z[window-1:,:] = np.squeeze(rolling_window(source,(window,source.shape[1]))).max(axis=1)
    return z

def minval(source,window):
    z = np.full_like(source,np.nan)
    z[window-1:,:] = np.squeeze(rolling_window(source,(window,source.shape[1]))).min(axis=1)
    return z