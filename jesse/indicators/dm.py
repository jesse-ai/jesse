from collections import namedtuple

import numpy as np

from jesse.helpers import slice_candles

DM = namedtuple('DM', ['plus', 'minus'])


def dm(candles: np.ndarray, period: int = 14, sequential: bool = False) -> DM:
    """
    DM - Directional Movement

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: DM(plus, minus)
    """
    candles = slice_candles(candles, sequential)
    high = candles[:, 3]
    low = candles[:, 4]
    n = len(high)

    # Compute raw directional movements
    raw_plus = np.full(n, np.nan)
    raw_minus = np.full(n, np.nan)
    if n > 0:
        raw_plus[0] = np.nan  # first value is undefined
        raw_minus[0] = np.nan
    if n > 1:
        diff_high = high[1:] - high[:-1]
        diff_low = low[:-1] - low[1:]
        plus = np.where((diff_high > diff_low) & (diff_high > 0), diff_high, 0)
        minus = np.where((diff_low > diff_high) & (diff_low > 0), diff_low, 0)
        raw_plus[1:] = plus
        raw_minus[1:] = minus

    # Apply Wilder's smoothing: the first valid smoothed value is at index 'period'
    smoothed_plus = np.full(n, np.nan, dtype=float)
    smoothed_minus = np.full(n, np.nan, dtype=float)
    if n > period:
        initial_plus = np.nansum(raw_plus[1:period+1])
        initial_minus = np.nansum(raw_minus[1:period+1])
        smoothed_plus[period] = initial_plus
        smoothed_minus[period] = initial_minus
        for i in range(period+1, n):
            smoothed_plus[i] = smoothed_plus[i-1] - (smoothed_plus[i-1] / period) + raw_plus[i]
            smoothed_minus[i] = smoothed_minus[i-1] - (smoothed_minus[i-1] / period) + raw_minus[i]

    if sequential:
        return DM(smoothed_plus, smoothed_minus)
    else:
        return DM(smoothed_plus[-1], smoothed_minus[-1])
