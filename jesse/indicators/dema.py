from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def _ema(x: np.ndarray, period: int) -> np.ndarray:
    alpha = 2 / (period + 1)
    n = len(x)
    # Create indices for constructing a lower triangular weight matrix
    i = np.arange(n)[:, None]  # shape (n, 1)
    j = np.arange(n)[None, :]   # shape (1, n)
    # For positions where j <= i, use alpha * (1-alpha)^(i-j); else 0
    weights = alpha * (1 - alpha) ** (i - j) * (j <= i)
    # Override the first column to implement the initial condition EMA[0] = x[0]
    weights[:, 0] = (1 - alpha) ** (np.arange(n))
    return weights.dot(x)


def dema(candles: np.ndarray, period: int = 30, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    DEMA - Double Exponential Moving Average

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

    # Calculate EMA using the custom _ema function and then compute DEMA
    ema = _ema(source, period)
    ema_of_ema = _ema(ema, period)
    res = 2 * ema - ema_of_ema

    return res if sequential else res[-1]
