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
        
        # Compute EMA using vectorized operations
        f = period - 1  # the index at which EMA calculation begins
        initial = np.mean(source[:period])
        L = len(source) - f  # number of points from the start of EMA calculation
        if L > 1:
            # X contains the source values after the initial period
            X = source[f+1:]
            # Create a lower-triangular matrix T of shape (L, L-1) where T[m, j] = (1-alpha)**(m-1-j) for j < m, else 0
            m_idx, j_idx = np.indices((L, L-1))
            T = np.where(j_idx < m_idx, (1 - alpha)**(m_idx - 1 - j_idx), 0)
            dot_sums = T.dot(X)
        else:
            dot_sums = np.zeros(L)
        m_vec = np.arange(L)
        y = (1 - alpha)**m_vec * initial + alpha * dot_sums
        result = np.full_like(source, np.nan, dtype=float)
        result[f:] = y

    return result if sequential else result[-1]
