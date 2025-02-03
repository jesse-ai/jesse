from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def trima(candles: np.ndarray, period: int = 30, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    TRIMA - Triangular Moving Average

    :param candles: np.ndarray
    :param period: int - default: 30
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    # Compute triangular weights
    if period % 2 != 0:
        mid = period // 2
        weights = np.concatenate((np.arange(1, mid + 2), np.arange(mid, 0, -1)))
    else:
        mid = period // 2
        weights = np.concatenate((np.arange(1, mid + 1), np.arange(mid, 0, -1)))
    weights_norm = weights / weights.sum()

    n = source.shape[0]
    if n < period:
        res = np.full(n, np.nan)
    else:
        conv = np.convolve(source, weights_norm, mode='valid')
        res = np.concatenate((np.full(period - 1, np.nan), conv))

    return res if sequential else res[-1]
