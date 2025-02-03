from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def var(candles: np.ndarray, period: int = 14, nbdev: float = 1, source_type: str = "close",
        sequential: bool = False) -> Union[float, np.ndarray]:
    """
    VAR - Variance

    :param candles: np.ndarray
    :param period: int - default: 14
    :param nbdev: float - default: 1
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    n = len(source)
    result = np.empty(n)
    result[:period-1] = np.nan
    if n >= period:
        windows = np.lib.stride_tricks.sliding_window_view(source, window_shape=period)
        window_mean = np.mean(windows, axis=1)
        window_mean_sq = np.mean(windows ** 2, axis=1)
        result[period-1:] = (window_mean_sq - window_mean**2) * nbdev
    else:
        result[:] = np.nan

    return result if sequential else result[-1]
