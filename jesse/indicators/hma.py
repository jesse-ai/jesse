from typing import Union
import numpy as np
from numba import njit
from jesse.helpers import get_candle_source, same_length, slice_candles


@njit
def _wma(arr: np.ndarray, period: int) -> np.ndarray:
    """
    Weighted Moving Average - optimized with Numba
    """
    weights = np.arange(1, period + 1)
    wma = np.zeros_like(arr)

    for i in range(period - 1, len(arr)):
        wma[i] = np.sum(arr[i - period + 1:i + 1] * weights) / np.sum(weights)

    return wma


def hma(candles: np.ndarray, period: int = 5, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    Hull Moving Average

    :param candles: np.ndarray
    :param period: int - default: 5
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    # Accept normal array too.
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    # Calculate components for HMA
    half_length = int(period / 2)
    sqrt_length = int(np.sqrt(period))

    # Calculate WMAs
    wma_half = _wma(source, half_length)
    wma_full = _wma(source, period)

    # Calculate 2 * WMA(n/2) - WMA(n)
    raw_hma = 2 * wma_half - wma_full

    # Calculate final HMA
    hma = _wma(raw_hma, sqrt_length)

    return same_length(candles, hma) if sequential else hma[-1]
