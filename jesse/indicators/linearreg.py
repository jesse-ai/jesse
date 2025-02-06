from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def linearreg(candles: np.ndarray, period: int = 14, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    LINEARREG - Linear Regression

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
    result = np.full(n, np.nan)
    if n >= period:
        try:
            from numpy.lib.stride_tricks import sliding_window_view
            windows = sliding_window_view(source, window_shape=period)  # shape (n - period + 1, period)
            mean_y = np.mean(windows, axis=1)
            x = np.arange(period)
            mean_x = (period - 1) / 2.0
            S_xx = np.sum((x - mean_x) ** 2)
            S_xy = np.sum((windows - mean_y[:, None]) * (x - mean_x), axis=1)
            values = mean_y + ((period - 1) / 2.0) * (S_xy / S_xx)
        except ImportError:
            values = []
            x = np.arange(period)
            mean_x = (period - 1) / 2.0
            S_xx = np.sum((x - mean_x) ** 2)
            for i in range(n - period + 1):
                window = source[i:i+period]
                mean_y = np.mean(window)
                S_xy = np.sum((window - mean_y) * (x - mean_x))
                values.append(mean_y + ((period - 1) / 2.0) * (S_xy / S_xx))
            values = np.array(values)
        result[period-1:] = values
    res = result

    return res if sequential else res[-1]
