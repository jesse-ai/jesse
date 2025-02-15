from typing import Union

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from jesse.helpers import slice_candles


def willr(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    WILLR - Williams' %R

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    # Extract required price series: close, high, and low
    close = candles[:, 2]
    high = candles[:, 3]
    low = candles[:, 4]
    n = len(candles)

    # Initialize result array with NaNs
    res = np.full(close.shape, np.nan, dtype=np.float64)

    # If there are not enough candles, return NaNs
    if n < period:
        return res if sequential else res[-1]

    # Compute rolling high and low using sliding_window_view for vectorized operations
    high_windows = sliding_window_view(high, window_shape=period)  # shape: (n - period + 1, period)
    low_windows = sliding_window_view(low, window_shape=period)

    rolling_max = np.max(high_windows, axis=1)
    rolling_min = np.min(low_windows, axis=1)

    denom = rolling_max - rolling_min
    close_window = close[period-1:]

    # Avoid division by zero: if denom is 0, set willr value to 0
    willr_values = ((rolling_max - close_window) / np.where(denom == 0, 1, denom)) * -100
    willr_values = np.where(denom == 0, 0, willr_values)

    res[period-1:] = willr_values
    return res if sequential else res[-1]
