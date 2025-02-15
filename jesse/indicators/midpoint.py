from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def midpoint(candles: np.ndarray, period: int = 14, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    MIDPOINT - MidPoint over period

    :param candles: np.ndarray
    :param period: int - default: 14
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    # If there is not enough data, return nan values
    if len(source) < period:
        if sequential:
            return np.full_like(source, np.nan)
        else:
            return np.nan

    # Use a sliding window to compute the midpoint: (max + min) / 2 over each rolling window
    windows = np.lib.stride_tricks.sliding_window_view(source, period)
    midpoints = (np.max(windows, axis=1) + np.min(windows, axis=1)) / 2.0

    # Pad the beginning with nans to match the input length if sequential is True
    if sequential:
        result = np.empty_like(source, dtype=float)
        result[:period - 1] = np.nan
        result[period - 1:] = midpoints
        return result
    else:
        return midpoints[-1]
