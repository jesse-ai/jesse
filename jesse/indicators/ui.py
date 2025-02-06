from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def ui(candles: np.ndarray, period: int = 14, scalar: float = 100, source_type: str = "close",  sequential: bool = False) -> Union[float, np.ndarray]:
    """
    Ulcer Index (UI)

    :param candles: np.ndarray
    :param period: int - default: 14
    :param scalar: float - default: 100
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    n = source.shape[0]

    # Compute rolling maximum over the period
    if n < period:
        highest_close = np.full_like(source, np.nan)
    else:
        # sliding_window_view creates a rolling window view: shape (n-period+1, period)
        highest_window = np.lib.stride_tricks.sliding_window_view(source, window_shape=period)
        highest_max = np.max(highest_window, axis=1)
        highest_close = np.concatenate((np.full(period - 1, np.nan), highest_max))

    # Calculate downside percentage
    downside = scalar * (source - highest_close) / highest_close
    d2 = downside ** 2

    # Compute rolling sum of squared downside values
    if n < period:
        rolling_d2_sum = np.full_like(d2, np.nan)
    else:
        rolling_sum_valid = np.convolve(d2, np.ones(period), mode='valid')
        rolling_d2_sum = np.concatenate((np.full(period - 1, np.nan), rolling_sum_valid))

    res = np.sqrt(rolling_d2_sum / period)

    return res if sequential else res[-1]
