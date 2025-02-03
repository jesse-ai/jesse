from typing import Union

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from jesse.helpers import slice_candles


def chop(candles: np.ndarray, period: int = 14, scalar: float = 100, drift: int = 1, sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Choppiness Index (CHOP)

    :param candles: np.ndarray
    :param period: int - default: 14
    :param scalar: float - default: 100
    :param drift: int - default: 1
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    candles_close = candles[:, 2]
    candles_high = candles[:, 3]
    candles_low = candles[:, 4]

    # Calculate True Range (TR)
    tr = np.empty_like(candles_close, dtype=float)
    tr[0] = candles_high[0] - candles_low[0]
    if drift == 1:
        d1 = candles_high[1:] - candles_low[1:]
        d2 = np.abs(candles_high[1:] - candles_close[:-1])
        d3 = np.abs(candles_low[1:] - candles_close[:-1])
        tr[1:] = np.maximum(np.maximum(d1, d2), d3)
        atr = tr
    else:
        d1 = candles_high[1:] - candles_low[1:]
        d2 = np.abs(candles_high[1:] - candles_close[:-1])
        d3 = np.abs(candles_low[1:] - candles_close[:-1])
        tr[1:] = np.maximum(np.maximum(d1, d2), d3)
        # Compute ATR using a vectorized approach for Wilder's smoothing
        alpha = 1.0 / drift
        n = len(tr)
        atr = np.full(n, np.nan, dtype=float)
        initial_atr = np.mean(tr[:drift])
        start = drift - 1  # index where initial ATR is placed
        M = n - start  # length of the subarray for ATR computation
        TR_sub = tr[start:]
        # Create a weight matrix for the exponential decay
        r = np.arange(M).reshape(-1, 1)  # row indices
        c = np.arange(M).reshape(1, -1)  # column indices
        weight_matrix = np.where((c > 0) & (c <= r), (1 - alpha) ** (r - c), 0.0)
        # For each row i, compute alpha * sum_{j=1}^{i} (1-alpha)^(i-j) * TR_sub[j]
        weighted_sum = alpha * np.sum(weight_matrix * TR_sub.reshape(1, -1), axis=1)
        # Add the contribution from the initial ATR: (1-alpha)^i * initial_atr
        atr_sub = weighted_sum + (1 - alpha) ** (np.arange(M)) * initial_atr
        atr[start:] = atr_sub

    # Calculate rolling sum of ATR over 'period'
    if len(atr) >= period:
        atr_windows = sliding_window_view(atr, window_shape=period)
        atr_sum = np.full_like(atr, np.nan, dtype=float)
        # Only assign sum if the window has no NaN
        valid = ~np.isnan(atr_windows).any(axis=-1)
        computed_sum = np.sum(atr_windows, axis=-1)
        atr_sum[period - 1:][valid] = computed_sum[valid]
    else:
        atr_sum = np.full_like(atr, np.nan, dtype=float)

    # Calculate rolling maximum of candles_high over 'period'
    if len(candles_high) >= period:
        high_windows = sliding_window_view(candles_high, window_shape=period)
        high_roll = np.max(high_windows, axis=-1)
        hh = np.full_like(candles_high, np.nan, dtype=float)
        hh[period - 1:] = high_roll
    else:
        hh = np.full_like(candles_high, np.nan, dtype=float)

    # Calculate rolling minimum of candles_low over 'period'
    if len(candles_low) >= period:
        low_windows = sliding_window_view(candles_low, window_shape=period)
        low_roll = np.min(low_windows, axis=-1)
        ll = np.full_like(candles_low, np.nan, dtype=float)
        ll[period - 1:] = low_roll
    else:
        ll = np.full_like(candles_low, np.nan, dtype=float)

    with np.errstate(divide='ignore', invalid='ignore'):
        res = (scalar * (np.log10(atr_sum) - np.log10(hh - ll))) / np.log10(period)

    return res if sequential else res[-1]
