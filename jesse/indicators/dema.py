from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, slice_candles

# Try to import the high-performance Rust implementation
try:
    from jesse_rust import dema as dema_rust  # type: ignore
except ImportError:  # pragma: no cover
    dema_rust = None  # type: ignore


@njit(cache=True)
def _ema(x: np.ndarray, period: int) -> np.ndarray:
    alpha = 2.0 / (period + 1)
    n = len(x)
    ema = np.empty(n, dtype=x.dtype)
    ema[0] = x[0]
    for i in range(1, n):
        ema[i] = alpha * x[i] + (1 - alpha) * ema[i - 1]
    return ema


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

    # Use Rust implementation if available
    if dema_rust is not None:
        # Convert to float64 for Rust compatibility
        source_f64 = np.asarray(source, dtype=np.float64)
        
        # Call the Rust implementation
        result = dema_rust(source_f64, period)
        
        return result if sequential else result[-1]
    else:
        # Fallback to Python implementation
        return _dema_python(source, period, sequential)


def _dema_python(source: np.ndarray, period: int, sequential: bool) -> Union[float, np.ndarray]:
    """Python fallback implementation."""
    ema = _ema(source, period)
    ema_of_ema = _ema(ema, period)
    res = 2 * ema - ema_of_ema

    return res if sequential else res[-1]
