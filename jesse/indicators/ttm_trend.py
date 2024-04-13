from typing import Union

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from jesse.helpers import get_candle_source, same_length, slice_candles


def ttm_trend(candles: np.ndarray, period: int = 5, source_type: str = "hl2", sequential: bool = False) -> Union[
        bool, np.ndarray]:
    """
    TTM Trend

    :param candles: np.ndarray
    :param period: int - default: 5
    :param source_type: str - default: "hl2"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    swv = sliding_window_view(source, window_shape=period)
    trend_avg = np.mean(swv, axis=-1)
    res = np.greater(candles[:, 2], same_length(source, trend_avg))

    return res if sequential else res[-1]
