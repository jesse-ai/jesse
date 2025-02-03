from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def linearreg_slope(candles: np.ndarray, period: int = 14, source_type: str = "close", sequential: bool = False) -> \
        Union[float, np.ndarray]:
    """
    LINEARREG_SLOPE - Linear Regression Slope

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

    n = len(source)
    result = np.full(n, np.nan, dtype=float)
    if n < period:
        return result if sequential else result[-1]

    # Create a constant x-axis for the regression
    X = np.arange(period, dtype=float)
    sumX = X.sum()
    sumX2 = (X**2).sum()
    denom = period * sumX2 - sumX**2

    # Compute the rolling window slopes using vectorized operations
    windows = np.lib.stride_tricks.sliding_window_view(source, window_shape=period)
    sum_y = windows.sum(axis=1)
    sum_xy = (windows * X).sum(axis=1)
    slopes = (period * sum_xy - sumX * sum_y) / denom

    result[period-1:] = slopes
    
    return result if sequential else result[-1]
