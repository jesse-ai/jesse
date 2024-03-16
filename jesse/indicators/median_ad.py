from typing import Union

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy import stats

from jesse.helpers import get_candle_source, same_length, slice_candles


def median_ad(candles: np.ndarray, period: int = 5, source_type: str = "hl2", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Median Absolute Deviation

    :param candles: np.ndarray
    :param period: int - default: 5
    :param source_type: str - default: "hl2"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """

    if len(candles.shape) == 1:
      source = candles
    else:
      candles = slice_candles(candles, sequential)
      source = get_candle_source(candles, source_type=source_type)

    swv = sliding_window_view(source, window_shape=period)
    median_abs_deviation = stats.median_abs_deviation(swv, axis=-1)
    res = same_length(source, median_abs_deviation)

    return res if sequential else res[-1]
