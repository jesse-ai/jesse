from typing import Union

import numpy as np
from scipy import stats
from numpy.lib.stride_tricks import sliding_window_view

from jesse.helpers import get_candle_source, slice_candles, same_length


def skew(candles: np.ndarray, period: int = 5, source_type: str = "hl2", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Skewness

    :param candles: np.ndarray
    :param period: int - default: 5
    :param source_type: str - default: "hl2"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    swv = sliding_window_view(source, window_shape=period)
    skewness = stats.skew(swv, axis=-1)
    res = same_length(source, skewness)

    return res if sequential else res[-1]
