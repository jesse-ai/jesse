from collections import namedtuple

import numpy as np

from jesse.helpers import slice_candles
from jesse.indicators.ma import ma

KDJ = namedtuple('KDJ', ['k', 'd', 'j'])

def _rolling_max(a, window):
    from numpy.lib.stride_tricks import sliding_window_view
    a = np.asarray(a)
    if len(a) < window:
        return np.maximum.accumulate(a)
    result = np.empty_like(a)
    # Use vectorized cumulative maximum for the first window-1 elements
    result[:window-1] = np.maximum.accumulate(a)[:window-1]
    windows = sliding_window_view(a, window_shape=window)
    result[window-1:] = np.max(windows, axis=1)
    return result

def _rolling_min(a, window):
    from numpy.lib.stride_tricks import sliding_window_view
    a = np.asarray(a)
    if len(a) < window:
        return np.minimum.accumulate(a)
    result = np.empty_like(a)
    # Use vectorized cumulative minimum for the first window-1 elements
    result[:window-1] = np.minimum.accumulate(a)[:window-1]
    windows = sliding_window_view(a, window_shape=window)
    result[window-1:] = np.min(windows, axis=1)
    return result

def kdj(candles: np.ndarray, fastk_period: int = 9, slowk_period: int = 3, slowk_matype: int = 0,
          slowd_period: int = 3, slowd_matype: int = 0, sequential: bool = False) -> KDJ:
    """
    The KDJ Oscillator

    :param candles: np.ndarray
    :param fastk_period: int - default: 9
    :param slowk_period: int - default: 3
    :param slowk_matype: int - default: 0
    :param slowd_period: int - default: 3
    :param slowd_matype: int - default: 0
    :param sequential: bool - default: False

    :return: KDJ(k, d, j)
    """
    if any(matype in (24, 29) for matype in (slowk_matype, slowd_matype)):
        raise ValueError("VWMA (matype 24) and VWAP (matype 29) cannot be used in kdj indicator.")
    
    candles = slice_candles(candles, sequential)

    candles_close = candles[:, 2]
    candles_high = candles[:, 3]
    candles_low = candles[:, 4]

    hh = _rolling_max(candles_high, fastk_period)
    ll = _rolling_min(candles_low, fastk_period)

    stoch = 100 * (candles_close - ll) / (hh - ll)
    
    k = ma(stoch, period=slowk_period, matype=slowk_matype, sequential=True)
    d = ma(k, period=slowd_period, matype=slowd_matype, sequential=True)
    j = 3 * k - 2 * d

    if sequential:
        return KDJ(k, d, j)
    else:
        return KDJ(k[-1], d[-1], j[-1])
