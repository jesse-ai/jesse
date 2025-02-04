from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def ema(candles: np.ndarray, period: int = 5, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    EMA - Exponential Moving Average

    :param candles: np.ndarray
    :param period: int - default: 5
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    if len(source) < period:
        result = np.full_like(source, np.nan, dtype=float)
    else:
        alpha = 2 / (period + 1)
        result = np.empty_like(source, dtype=float)
        for i in range(len(source)):
            if i < period - 1:
                result[i] = np.nan
            elif i == period - 1:
                result[i] = np.mean(source[:period])
            else:
                result[i] = alpha * source[i] + (1 - alpha) * result[i-1]

    return result if sequential else result[-1]
