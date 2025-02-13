import numpy as np
from typing import Union

from jesse.helpers import slice_candles


def natr(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    NATR - Normalized Average True Range

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]

    # Compute True Range (TR)
    n = len(candles)
    tr = np.empty(n, dtype=float)
    tr[0] = high[0] - low[0]
    if n > 1:
        diff1 = high[1:] - low[1:]
        diff2 = np.abs(high[1:] - close[:-1])
        diff3 = np.abs(low[1:] - close[:-1])
        tr[1:] = np.maximum(np.maximum(diff1, diff2), diff3)

    # Initialize ATR array
    atr = np.empty(n, dtype=float)
    atr[:period-1] = np.nan  # not enough data for smoothing
    base = np.mean(tr[:period])
    atr[period-1] = base

    # If there's no additional data after the initial period, return the current NATR
    if n == period:
        result = (base / close[period-1]) * 100
        return result if not sequential else np.concatenate((np.full(period-1, np.nan), [result]))

    # Wilder's smoothing is equivalent to an exponential moving average with alpha = 1/period
    alpha = 1.0 / period
    beta = 1 - alpha
    # For indices from period to end, we compute the recursive ATR as:
    # ATR[t] = beta^(t - (period-1)) * base + sum_{i=period}^{t} (alpha * beta^(t-i) * tr[i])
    # We vectorize the summation using convolution.
    x = tr[period:]
    m = len(x)
    weights = alpha * beta ** np.arange(m)
    conv = np.convolve(x, weights, mode='full')[:m]
    base_adjustment = beta ** (np.arange(1, m + 1)) * base
    atr[period:] = base_adjustment + conv

    natr_arr = (atr / close) * 100
    return natr_arr if sequential else natr_arr[-1]
