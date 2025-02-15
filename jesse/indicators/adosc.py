from typing import Union

import numpy as np
from numba import njit
from jesse.helpers import slice_candles


@njit(cache=True)
def compute_multiplier(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    n = high.shape[0]
    out = np.empty(n, dtype=high.dtype)
    for i in range(n):
        rng = high[i] - low[i]
        if rng != 0:
            out[i] = ((close[i] - low[i]) - (high[i] - close[i])) / rng
        else:
            out[i] = 0.0
    return out


@njit(cache=True)
def elementwise_multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    n = a.shape[0]
    out = np.empty(n, dtype=a.dtype)
    for i in range(n):
        out[i] = a[i] * b[i]
    return out


@njit(cache=True)
def cumulative_sum(arr: np.ndarray) -> np.ndarray:
    n = arr.shape[0]
    out = np.empty(n, dtype=arr.dtype)
    total = 0.0
    for i in range(n):
        total += arr[i]
        out[i] = total
    return out


@njit(cache=True)
def ema(values: np.ndarray, period: int) -> np.ndarray:
    n = values.shape[0]
    result = np.empty(n, dtype=values.dtype)
    alpha = 2.0 / (period + 1)
    result[0] = values[0]
    for i in range(1, n):
        result[i] = alpha * values[i] + (1.0 - alpha) * result[i - 1]
    return result


@njit(cache=True)
def subtract_arrays(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    n = a.shape[0]
    out = np.empty(n, dtype=a.dtype)
    for i in range(n):
        out[i] = a[i] - b[i]
    return out


def adosc(candles: np.ndarray, fast_period: int = 3, slow_period: int = 10, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    ADOSC - Chaikin A/D Oscillator (Numba accelerated version)

    :param candles: np.ndarray of candles
    :param fast_period: int - default: 3
    :param slow_period: int - default: 10
    :param sequential: bool - default: False
    :return: float or np.ndarray
    """
    candles = slice_candles(candles, sequential)
    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]
    volume = candles[:, 5]

    multiplier = compute_multiplier(high, low, close)
    mf_volume = elementwise_multiply(multiplier, volume)
    ad_line = cumulative_sum(mf_volume)

    fast_ema = ema(ad_line, fast_period)
    slow_ema = ema(ad_line, slow_period)
    adosc_vals = subtract_arrays(fast_ema, slow_ema)

    return adosc_vals if sequential else adosc_vals[-1]
