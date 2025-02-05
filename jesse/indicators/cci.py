from typing import Union

import numpy as np

from jesse.helpers import slice_candles


def cci(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    CCI - Commodity Channel Index

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]
    tp = (high + low + close) / 3.0

    result = np.full(tp.shape, np.nan)
    if tp.shape[0] < period:
        if sequential:
            return result
        else:
            return np.nan

    # Compute rolling window of typical prices
    windows = np.lib.stride_tricks.sliding_window_view(tp, window_shape=period)
    sma = np.mean(windows, axis=1)
    md = np.mean(np.abs(windows - sma[:, None]), axis=1)
    cci_values = np.where(md == 0, 0, (tp[period - 1:] - sma) / (0.015 * md))
    result[period - 1:] = cci_values

    return result if sequential else result[-1]
