from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def cmo(candles: np.ndarray, period: int = 14, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    CMO - Chande Momentum Oscillator

    :param candles: np.ndarray
    :param period: int - default: 14
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    diff = np.diff(source)
    result = np.full(source.shape, np.nan, dtype=float)
    if len(diff) >= period:
        # Create a sliding window of differences of shape (len(source)-period, period)
        windows = np.lib.stride_tricks.sliding_window_view(diff, window_shape=period)
        pos_sum = np.where(windows > 0, windows, 0).sum(axis=1)
        neg_sum = np.where(windows < 0, -windows, 0).sum(axis=1)
        denom = pos_sum + neg_sum
        cmo_vals = np.where(denom == 0, 0, 100 * (pos_sum - neg_sum) / denom)
        # Assign computed CMO values starting at index 'period'
        result[period:] = cmo_vals
    return result if sequential else result[-1]
