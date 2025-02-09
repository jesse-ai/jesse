from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def weighted_moving_average_custom(source: np.ndarray, period: int) -> np.ndarray:
    weights = np.arange(1, period + 1)
    weight_sum = weights.sum()
    result = np.full(len(source), np.nan, dtype=float)
    if len(source) < period:
        return result
    windowed = np.lib.stride_tricks.sliding_window_view(source, period)
    result[period-1:] = np.dot(windowed, weights) / weight_sum
    return result


def wma(candles: np.ndarray, period: int = 30, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    WMA - Weighted Moving Average

    :param candles: np.ndarray
    :param period: int - default: 30
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    res = weighted_moving_average_custom(source, period)
    return res if sequential else res[-1]
