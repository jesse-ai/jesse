from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def linearreg_intercept(candles: np.ndarray, period: int = 14, source_type: str = "close", sequential: bool = False) -> \
        Union[float, np.ndarray]:
    """
    LINEARREG_INTERCEPT - Linear Regression Intercept

    :param candles: np.ndarray
    :param period: int - default: 14
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    # Compute linear regression intercept using vectorized operations 
    if len(source) < period:
        if sequential:
            return np.full_like(source, np.nan, dtype=float)
        else:
            return np.nan

    x = np.arange(period, dtype=float)
    x_mean = x.mean()
    sxx = ((x - x_mean) ** 2).sum()

    if sequential:
        # Compute rolling windows using a vectorized approach
        windows = np.lib.stride_tricks.sliding_window_view(source, window_shape=period)
        means = windows.mean(axis=1)
        slopes = np.dot(windows - means[:, None], (x - x_mean)) / sxx
        intercepts = means - slopes * x_mean
        result = np.concatenate((np.full(period - 1, np.nan), intercepts))
        return result
    else:
        window = source[-period:]
        mean_val = window.mean()
        slope = np.dot(window - mean_val, (x - x_mean)) / sxx
        intercept = mean_val - slope * x_mean
        return intercept
