from typing import Union

import numpy as np
from numba import njit

import jesse.helpers as jh
from jesse.helpers import slice_candles


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
    DTI by William Blau calculated using numba accelerated EMA loops.

    :param candles: np.ndarray of candles data
    :param r: period for the first EMA smoothing (default 14)
    :param s: period for the second EMA smoothing (default 10)
    :param u: period for the third EMA smoothing (default 5)
    :param sequential: if True, returns the full sequence, otherwise only the last value
    :return: float or np.ndarray of DTI values
    """
    candles = slice_candles(candles, sequential)
    high = candles[:, 3]
    low = candles[:, 4]

    high_1 = jh.np_shift(high, 1, np.nan)
    low_1 = jh.np_shift(low, 1, np.nan)

    # Compute upward and downward movements
    xHMU = np.where(high - high_1 > 0, high - high_1, 0)
    xLMD = np.where(low - low_1 < 0, -(low - low_1), 0)

    xPrice = xHMU - xLMD
    xPriceAbs = np.abs(xPrice)

    # Apply triple EMA using the numba accelerated _ema
    temp = _ema(xPrice, r)
    temp = _ema(temp, s)
    xuXA = _ema(temp, u)

    temp_abs = _ema(xPriceAbs, r)
    temp_abs = _ema(temp_abs, s)
    xuXAAbs = _ema(temp_abs, u)

    Val1 = 100 * xuXA
    Val2 = xuXAAbs
    with np.errstate(divide='ignore', invalid='ignore'):
        dti_val = np.divide(Val1, Val2, out=np.zeros_like(Val1, dtype=float), where=Val2 != 0)

    if sequential:
        return dti_val
    else:
        return None if np.isnan(dti_val[-1]) else dti_val[-1]
