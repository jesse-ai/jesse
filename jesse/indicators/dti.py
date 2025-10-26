from typing import Union

import numpy as np
from numba import njit

import jesse.helpers as jh
from jesse.helpers import slice_candles
import jesse_rust as jr


@njit(cache=True)
def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    """
    Compute the exponential moving average (EMA) using a simple for loop, accelerated with numba.
    The formula is: EMA[i] = sum_{j=0}^{i} (alpha * (1-alpha)**(i - j) * arr[j]) where alpha = 2/(period+1).
    This is computed iteratively:
      EMA[0] = alpha * arr[0]
      EMA[i] = alpha * arr[i] + (1 - alpha) * EMA[i-1] for i >= 1
    """
    alpha = 2.0 / (period + 1)
    n = arr.shape[0]
    result = np.empty(n, dtype=arr.dtype)
    result[0] = alpha * arr[0]
    for i in range(1, n):
        result[i] = alpha * arr[i] + (1 - alpha) * result[i - 1]
    return result


def dti(candles: np.ndarray, r: int = 14, s: int = 10, u: int = 5, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    DTI by William Blau calculated using Rust implementation for better performance.

    :param candles: np.ndarray of candles data
    :param r: period for the first EMA smoothing (default 14)
    :param s: period for the second EMA smoothing (default 10)
    :param u: period for the third EMA smoothing (default 5)
    :param sequential: if True, returns the full sequence, otherwise only the last value
    :return: float or np.ndarray of DTI values
    """
    candles = slice_candles(candles, sequential)
    
    # Use the Rust implementation
    res = jr.dti(candles, r, s, u)
    
    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
