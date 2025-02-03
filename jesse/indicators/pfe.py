from typing import Union

import numpy as np

from numba import njit
from jesse.helpers import get_candle_source, same_length, slice_candles

@njit(cache=True)
def numpy_ema(data: np.ndarray, period: int) -> np.ndarray:
    alpha = 2 / (period + 1)
    # Initialize the EMA with the first value
    ema = np.zeros_like(data)
    ema[0] = data[0]
    # Calculate EMA using vectorized operations
    for i in range(1, len(data)):
        ema[i] = data[i] * alpha + ema[i-1] * (1 - alpha)
    return ema


def rolling_sum(arr: np.ndarray, window: int) -> np.ndarray:
    # Create a rolling window sum using convolution
    window_ones = np.ones(window)
    sum_result = np.convolve(arr, window_ones, mode='valid')
    # Pad the beginning to maintain array length
    padding = np.array([np.nan] * (len(arr) - len(sum_result)))
    return np.concatenate((padding, sum_result))


def pfe(candles: np.ndarray, period: int = 10, smoothing: int = 5, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Polarized Fractal Efficiency (PFE)

    :param candles: np.ndarray
    :param period: int - default: 10
    :param smoothing: int - default: 5
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    ln = period - 1
    diff = np.diff(source, ln)
    a = np.sqrt(np.power(diff, 2) + np.power(period, 2))
    
    # Calculate rolling sum of sqrt(1 + diff^2)
    diff_1 = np.diff(source, 1)
    sqrt_term = np.sqrt(1 + np.power(diff_1, 2))
    b = rolling_sum(sqrt_term, ln)
    
    pfetmp = 100 * same_length(source, a) / same_length(source, b)
    # Replace NaN values with 0 to avoid issues in calculations
    pfetmp = np.nan_to_num(pfetmp, 0)
    
    # Calculate the sign based on diff
    sign = np.where(same_length(source, diff) > 0, 1, -1)
    res = numpy_ema(sign * pfetmp, smoothing)

    return res if sequential else res[-1]
