from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def cfo(candles: np.ndarray, period: int = 14, scalar: float = 100, source_type: str = "close",
        sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    CFO - Chande Forcast Oscillator

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
    reg = np.full_like(source, np.nan, dtype=np.float64)
    if n >= period:
        # Create rolling windows of length 'period'
        windows = np.lib.stride_tricks.sliding_window_view(source, period)

        # x values: 0, 1, ..., period-1
        x = np.arange(period, dtype=np.float64)
        Sx = x.sum()
        Sxx = (x * x).sum()
        denom = period * Sxx - Sx * Sx

        # Compute rolling sums within each window
        sum_y = windows.sum(axis=1)
        sum_xy = (windows * x).sum(axis=1)

        slope = (period * sum_xy - Sx * sum_y) / denom
        intercept = (sum_y - slope * Sx) / period
        reg_values = intercept + slope * (period - 1)
        reg[period - 1:] = reg_values

    res = scalar * (source - reg) / source

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
