from collections import namedtuple

import numpy as np

from jesse.helpers import slice_candles

# Try to import the high-performance Rust implementation
try:
    from jesse.rust import stochf as stochf_rust  # type: ignore
except ImportError:  # pragma: no cover
    stochf_rust = None  # type: ignore

StochasticFast = namedtuple('StochasticFast', ['k', 'd'])

def stochf(candles: np.ndarray, fastk_period: int = 5, fastd_period: int = 3, fastd_matype: int = 0,
           sequential: bool = False) -> StochasticFast:
    """
    Stochastic Fast

    :param candles: np.ndarray
    :param fastk_period: int - default: 5
    :param fastd_period: int - default: 3
    :param fastd_matype: int - default: 0
    :param sequential: bool - default: False

    :return: StochasticFast(k, d)
    """
    if fastd_matype == 24 or fastd_matype == 29:
        raise ValueError("VWMA (matype 24) and VWAP (matype 29) cannot be used in stochf indicator.")

    candles = slice_candles(candles, sequential)

    # Use Rust implementation if available
    if stochf_rust is not None:
        # Convert to float64 for Rust compatibility
        candles_f64 = np.asarray(candles, dtype=np.float64)
        
        # Call the Rust implementation
        k, d = stochf_rust(candles_f64, fastk_period, fastd_period, fastd_matype)
        
        if sequential:
            return StochasticFast(k, d)
        else:
            return StochasticFast(k[-1], d[-1])
    else:
        # Fallback to Python implementation
        return _stochf_python(candles, fastk_period, fastd_period, fastd_matype, sequential)


def _stochf_python(candles: np.ndarray, fastk_period: int, fastd_period: int, fastd_matype: int,
                   sequential: bool) -> StochasticFast:
    """Python fallback implementation."""
    from jesse.indicators.ma import ma
    
    candles_close = candles[:, 2]
    candles_high = candles[:, 3]
    candles_low = candles[:, 4]

    hh = _rolling_max(candles_high, fastk_period)
    ll = _rolling_min(candles_low, fastk_period)

    k = 100 * (candles_close - ll) / (hh - ll)
    d = ma(k, period=fastd_period, matype=fastd_matype, sequential=True)

    if sequential:
        return StochasticFast(k, d)
    else:
        return StochasticFast(k[-1], d[-1])

def _rolling_min(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.shape[0]
    if n < window:
        return np.minimum.accumulate(arr)
    out = np.empty_like(arr)
    if window > 1:
        out[:window-1] = np.minimum.accumulate(arr[:window-1])
    view = np.lib.stride_tricks.sliding_window_view(arr, window_shape=window)
    out[window-1:] = np.min(view, axis=-1)
    return out

def _rolling_max(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.shape[0]
    if n < window:
        return np.maximum.accumulate(arr)
    out = np.empty_like(arr)
    if window > 1:
        out[:window-1] = np.maximum.accumulate(arr[:window-1])
    view = np.lib.stride_tricks.sliding_window_view(arr, window_shape=window)
    out[window-1:] = np.max(view, axis=-1)
    return out
