from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles
from jesse.indicators.ma import ma


def rolling_window(a, window):
    """
    Create a rolling window of the array for vectorized operations
    """
    shape = a.shape[:-1] + (a.shape[-1] - window + 1, window)
    strides = a.strides + (a.strides[-1],)
    return np.lib.stride_tricks.as_strided(a, shape=shape, strides=strides)


def rolling_min(arr: np.ndarray, window: int) -> np.ndarray:
    """
    Calculate rolling minimum using numpy operations
    """
    result = np.empty_like(arr)
    result[:window-1] = arr[:window-1]  # Keep original values for the first window-1 elements
    result[window-1:] = np.min(rolling_window(arr, window), axis=1)
    return result


def rolling_max(arr: np.ndarray, window: int) -> np.ndarray:
    """
    Calculate rolling maximum using numpy operations
    """
    result = np.empty_like(arr)
    result[:window-1] = arr[:window-1]  # Keep original values for the first window-1 elements
    result[window-1:] = np.max(rolling_window(arr, window), axis=1)
    return result


def stc(candles: np.ndarray, fast_period: int = 23, fast_matype: int = 1, slow_period: int = 50, slow_matype: int = 1,
        k_period: int = 10, d_period: int = 3,
        source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    STC - Schaff Trend Cycle (Oscillator)

    :param candles: np.ndarray
    :param fast_period: int - default: 23
    :param fast_matype: int - default: 1
    :param slow_period: int - default: 50
    :param slow_matype: int - default: 1
    :param k_period: int - default: 10
    :param d_period: int - default: 3
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    # Calculate MACD
    macd = ma(source, period=fast_period, matype=fast_matype, sequential=True) - ma(source, period=slow_period, matype=slow_matype, sequential=True)

    # Calculate %K
    macd_min = rolling_min(macd, k_period)
    macd_max = rolling_max(macd, k_period)
    stok = np.zeros_like(macd)
    valid_denom = (macd_max - macd_min) != 0
    stok[valid_denom] = (macd[valid_denom] - macd_min[valid_denom]) / (macd_max[valid_denom] - macd_min[valid_denom]) * 100

    # First smoothing using EMA
    d = ma(stok, period=d_period, matype=1, sequential=True)  # matype=1 is EMA

    # Calculate second %K
    d_min = rolling_min(d, k_period)
    d_max = rolling_max(d, k_period)
    kd = np.zeros_like(d)
    valid_denom = (d_max - d_min) != 0
    kd[valid_denom] = (d[valid_denom] - d_min[valid_denom]) / (d_max[valid_denom] - d_min[valid_denom]) * 100

    # Second smoothing using EMA
    res = ma(kd, period=d_period, matype=1, sequential=True)  # matype=1 is EMA

    return res if sequential else res[-1]
