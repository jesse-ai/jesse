from typing import Union

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from jesse.helpers import get_candle_source, same_length, slice_candles
from jesse.indicators.ma import ma
from jesse.indicators.mean_ad import mean_ad
from jesse.indicators.median_ad import median_ad

def rvi(candles: np.ndarray, period: int = 10, ma_len: int = 14, matype: int = 1, devtype: int = 0, source_type: str = "close",
        sequential: bool = False) -> Union[float, np.ndarray]:
    """
    RVI - Relative Volatility Index
    :param candles: np.ndarray
    :param period: int - default: 10
    :param ma_len: int - default: 14
    :param matype: int - default: 1
    :param devtype: int - default: 0
    :param source_type: str - default: "close"
    :param sequential: bool - default: False
    :return: float | np.ndarray
    """
    if matype == 24 or matype == 29:
        raise ValueError("VWMA (matype 24) and VWAP (matype 29) cannot be used in rvi indicator.")

    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    if devtype == 0:
      dev = _rolling_std(source, period)
    elif devtype == 1:
      dev = mean_ad(source, period, sequential=True)
    elif devtype == 2:
      dev = median_ad(source, period, sequential=True)

    diff = np.diff(source)
    diff = same_length(source, diff)

    up = np.nan_to_num(np.where(diff <= 0, 0, dev))
    down = np.nan_to_num(np.where(diff > 0, 0, dev))

    up_avg = ma(up, period=ma_len, matype=matype, sequential=True)
    down_avg = ma(down, period=ma_len, matype=matype, sequential=True)

    result = 100 * (up_avg / (up_avg + down_avg))

    return result if sequential else result[-1]


def _rolling_std(arr: np.ndarray, window: int) -> np.ndarray:
    if len(arr) < window:
        return np.full(len(arr), np.nan)
    windows = sliding_window_view(arr, window_shape=window)
    stds = np.std(windows, axis=1, ddof=0)
    return np.concatenate((np.full(window - 1, np.nan), stds))
