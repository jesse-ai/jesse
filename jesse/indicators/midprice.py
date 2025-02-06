from typing import Union

import numpy as np
from jesse.helpers import slice_candles
from numpy.lib.stride_tricks import sliding_window_view


def midprice(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    MIDPRICE - Midpoint Price over period

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    high = candles[:, 3]
    low = candles[:, 4]

    if sequential:
        n = len(candles)
        if n < period:
            return np.full(n, np.nan)

        # Create sliding windows for high and low prices
        windows_high = sliding_window_view(high, window_shape=period)
        windows_low = sliding_window_view(low, window_shape=period)

        # Calculate midprice for each window
        midprices = (np.max(windows_high, axis=1) + np.min(windows_low, axis=1)) / 2

        # Prepend NaN for the initial period-1 values to match the typical TA-Lib output length
        result = np.concatenate((np.full(period - 1, np.nan), midprices))
        return result
    else:
        if len(candles) < period:
            return np.nan
        return (np.max(high[-period:]) + np.min(low[-period:])) / 2
