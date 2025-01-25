from typing import Union

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from jesse.helpers import get_candle_source, same_length, slice_candles


def vwma(candles: np.ndarray, period: int = 20, source_type: str = "close", sequential: bool = False) -> Union[
        float, np.ndarray]:
    """
    VWMA - Volume Weighted Moving Average

    :param candles: np.ndarray
    :param period: int - default: 20
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
        volume = np.ones_like(candles)
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
        volume = candles[:, 5]

    # Calculate price * volume
    weighted_price = source * volume

    # Use sliding window to calculate sums
    price_sum = np.sum(sliding_window_view(weighted_price, period), axis=1)
    volume_sum = np.sum(sliding_window_view(volume, period), axis=1)

    # Calculate VWMA and handle division by zero
    res = np.zeros_like(source)
    res[period-1:] = price_sum / np.where(volume_sum == 0, 1, volume_sum)

    return same_length(candles, res) if sequential else res[-1]
