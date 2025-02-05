from typing import Union

import numpy as np

from jesse.helpers import slice_candles


def atr(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    ATR - Average True Range

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]

    # Compute previous close by shifting the close array; for the first element, use itself
    prev_close = np.empty_like(close)
    prev_close[0] = close[0]
    prev_close[1:] = close[:-1]

    # Calculate True Range
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    tr[0] = high[0] - low[0]  # ensure first element is high - low

    # Initialize ATR array
    atr_values = np.empty_like(tr)
    # For indices with insufficient data, set to NaN
    atr_values[:period-1] = np.nan
    # First ATR value is the simple average of the first 'period' true ranges
    atr_values[period-1] = np.mean(tr[:period])

    # Compute subsequent ATR values using Wilder's smoothing method (vectorized implementation)
    y0 = atr_values[period-1]  # initial ATR value (simple average of first period true ranges)
    n_rest = len(tr) - period
    if n_rest > 0:
        alpha = 1.0 / period
        beta = (period - 1) / period  # equivalent to 1 - alpha
        indices = np.arange(1, n_rest + 1)
        first_term = y0 * (beta ** indices)
        # Create a lower-triangular matrix where L[i, j] = beta^(i - j) for j<=i
        L = np.tril(beta ** (np.subtract.outer(np.arange(n_rest), np.arange(n_rest))))
        atr_values[period:] = first_term + alpha * np.dot(L, tr[period:])

    return atr_values if sequential else atr_values[-1]
