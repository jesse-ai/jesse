from typing import Union

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from jesse.helpers import slice_candles


def beta(candles: np.ndarray, benchmark_candles: np.ndarray, period: int = 5, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    BETA - compares the given candles close price to its benchmark (should be in the same time frame)

    :param candles: np.ndarray
    :param benchmark_candles: np.ndarray
    :param period: int - default: 5
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    benchmark_candles = slice_candles(benchmark_candles, sequential)

    x = candles[:, 2]
    y = benchmark_candles[:, 2]

    if len(x) < period:
        out = np.full_like(x, fill_value=np.nan, dtype=float)
        return out if sequential else np.nan

    windows_x = sliding_window_view(x, window_shape=period)
    windows_y = sliding_window_view(y, window_shape=period)

    mean_x = windows_x.mean(axis=1)
    mean_y = windows_y.mean(axis=1)

    diff_x = windows_x - mean_x[:, None]
    diff_y = windows_y - mean_y[:, None]

    numerator = (diff_x * diff_y).sum(axis=1)
    denominator = (diff_y ** 2).sum(axis=1)

    with np.errstate(divide='ignore', invalid='ignore'):
         beta_vals = numerator / denominator

    out = np.full_like(x, fill_value=np.nan, dtype=float)
    out[period - 1:] = beta_vals

    return out if sequential else out[-1]
