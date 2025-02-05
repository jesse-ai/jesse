from typing import Union

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from jesse.helpers import slice_candles
from jesse.indicators.mean_ad import mean_ad
from jesse.indicators.median_ad import median_ad


def devstop(candles: np.ndarray, period: int = 20, mult: float = 0, devtype: int = 0, direction: str = "long",
            sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Kase Dev Stops

    :param candles: np.ndarray
    :param period: int - default: 20
    :param mult: float - default: 0
    :param devtype: int - default: 0
    :param direction: str - default: long
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    high = candles[:, 3]
    low = candles[:, 4]

    AVTR = rolling_mean(rolling_max(high, 2) - rolling_min(low, 2), period)

    if devtype == 0:
       SD = rolling_std(rolling_max(high, 2) - rolling_min(low, 2), period)
    elif devtype == 1:
       SD = mean_ad(rolling_max(high, 2) - rolling_min(low, 2), period, sequential=True)
    elif devtype == 2:
       SD = median_ad(rolling_max(high, 2) - rolling_min(low, 2), period, sequential=True)

    if direction == "long":
        res = rolling_max(high - AVTR - mult * SD, period)
    else:
        res = rolling_min(low + AVTR + mult * SD, period)

    return res if sequential else res[-1]

def rolling_max(arr, window):
    if len(arr) < window:
        return np.full(arr.shape, np.nan)
    windows = sliding_window_view(arr, window)
    res = np.empty(len(arr))
    res[:window-1] = np.nan
    res[window-1:] = np.max(windows, axis=1)
    return res

def rolling_min(arr, window):
    if len(arr) < window:
        return np.full(arr.shape, np.nan)
    windows = sliding_window_view(arr, window)
    res = np.empty(len(arr))
    res[:window-1] = np.nan
    res[window-1:] = np.min(windows, axis=1)
    return res

def rolling_mean(arr, window):
    if len(arr) < window:
        return np.full(arr.shape, np.nan)
    windows = sliding_window_view(arr, window)
    res = np.empty(len(arr))
    res[:window-1] = np.nan
    res[window-1:] = np.mean(windows, axis=1)
    return res

def rolling_std(arr, window):
    if len(arr) < window:
        return np.full(arr.shape, np.nan)
    windows = sliding_window_view(arr, window)
    res = np.empty(len(arr))
    res[:window-1] = np.nan
    res[window-1:] = np.std(windows, axis=1, ddof=0)
    return res
