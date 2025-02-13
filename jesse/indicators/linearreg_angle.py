from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def linearreg_angle(candles: np.ndarray, period: int = 14, source_type: str = "close", sequential: bool = False) -> \
        Union[float, np.ndarray]:
    """
    LINEARREG_ANGLE - Linear Regression Angle

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

    N = len(source)
    res = np.full(N, np.nan)
    if N >= period:
        # Create rolling windows of length 'period'
        windows = np.lib.stride_tricks.sliding_window_view(source, window_shape=period)
        x = np.arange(period)
        sum_x = x.sum()
        sum_x2 = (x * x).sum()
        common_den = period * sum_x2 - sum_x ** 2
        sum_y = np.sum(windows, axis=1)
        sum_xy = windows.dot(x)
        slopes = (period * sum_xy - sum_x * sum_y) / common_den
        angles = np.degrees(np.arctan(slopes))
        res[period - 1:] = angles
    return res if sequential else res[-1]
