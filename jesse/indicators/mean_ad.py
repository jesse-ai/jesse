from typing import Union

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from jesse.helpers import get_candle_source, slice_candles, same_length


def mean_ad(candles: np.ndarray, period: int = 5, source_type: str = "hl2", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Mean Absolute Deviation

    :param candles: np.ndarray
    :param period: int - default: 5
    :param source_type: str - default: "hl2"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
      source = candles
    else:
      candles = slice_candles(candles, sequential)
      source = get_candle_source(candles, source_type=source_type)

    swv = sliding_window_view(source, window_shape=period)
    abs_diff = np.absolute(source - same_length(source, np.mean(swv, -1)))
    smv_abs_diff = sliding_window_view(abs_diff, window_shape=period)
    mean_abs_deviation = np.nanmean(smv_abs_diff, -1)
    res = same_length(source, mean_abs_deviation)

    return res if sequential else res[-1]

