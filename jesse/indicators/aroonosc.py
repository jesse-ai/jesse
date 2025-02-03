from typing import Union

import numpy as np

from jesse.helpers import slice_candles


def aroonosc(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    AROONOSC - Aroon Oscillator

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    high = candles[:, 3]
    low = candles[:, 4]
    n = len(high)

    if n < period:
        result = np.full(n, np.nan)
    else:
        # Use sliding_window_view for vectorized window computation
        windows_high = np.lib.stride_tricks.sliding_window_view(high, window_shape=period)
        windows_low = np.lib.stride_tricks.sliding_window_view(low, window_shape=period)

        # Find the index of the highest high and the lowest low in each window
        idx_max = np.argmax(windows_high, axis=1)
        idx_min = np.argmin(windows_low, axis=1)

        # Calculate Aroon Oscillator: Aroon Up = ((idx_max + 1) / period) * 100, Aroon Down = ((idx_min + 1) / period) * 100
        # oscillator = Aroon Up - Aroon Down = 100*(idx_max - idx_min)/period
        aroonosc_values = 100 * (idx_max - idx_min) / period

        result = np.concatenate((np.full(period - 1, np.nan), aroonosc_values))

    return result if sequential else result[-1]
