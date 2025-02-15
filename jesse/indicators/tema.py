from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles

def tema(candles: np.ndarray, period: int = 9, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    TEMA - Triple Exponential Moving Average

    :param candles: np.ndarray
    :param period: int - default: 9
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    ema1 = _ema(source, period)
    ema2 = _ema(ema1, period)
    ema3 = _ema(ema2, period)
    res = 3 * ema1 - 3 * ema2 + ema3
    return res if sequential else res[-1]

def _ema(x: np.ndarray, period: int) -> np.ndarray:
    n = len(x)
    if n == 0:
        return x
    alpha = 2.0 / (period + 1.0)
    idx = np.arange(n)
    # Compute a lower triangular matrix of differences i - j
    diff = np.subtract.outer(idx, idx)
    mask = np.tril(np.ones((n, n), dtype=bool))
    # For j > 0, weight = alpha*(1-alpha)^(i-j), but for j==0, use (1-alpha)^i as seed
    W = alpha * np.power((1 - alpha), diff) * mask
    W[:, 0] = np.power((1 - alpha), idx)
    return np.dot(W, x)

