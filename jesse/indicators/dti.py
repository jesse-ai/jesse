from typing import Union

import numpy as np

import jesse.helpers as jh
from jesse.helpers import slice_candles


def ema_vec(data: np.ndarray, period: int) -> np.ndarray:
    """
    Compute exponential moving average (EMA) using vectorized matrix multiplication.
    The formula is: EMA[i] = sum_{j=0}^{i} (alpha * (1-alpha)**(i - j) * data[j])
    where alpha = 2/(period+1).
    :param data: np.ndarray of values
    :param period: int, period for EMA
    :return: np.ndarray of EMA values, same shape as data
    """
    alpha = 2 / (period + 1)
    n = len(data)
    indices = np.arange(n)
    # Create a lower-triangular weights matrix where for each row i, weights[i, j] = alpha*(1-alpha)**(i-j) for j<=i, else 0
    weights = np.where(indices[:, None] >= indices[None, :], alpha * (1 - alpha) ** (indices[:, None] - indices[None, :]), 0)
    return weights.dot(data)


def dti(candles: np.ndarray, r: int = 14, s: int = 10, u: int = 5, sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    DTI by William Blau

    :param candles: np.ndarray
    :param r: int - default: 14
    :param s: int - default: 10
    :param u: int - default: 5
    :param sequential: bool - default: False

    :return: float
    """
    candles = slice_candles(candles, sequential)

    high = candles[:, 3]
    low = candles[:, 4]

    high_1 = jh.np_shift(high, 1, np.nan)
    low_1 = jh.np_shift(low, 1, np.nan)

    xHMU = np.where(high - high_1 > 0, high - high_1, 0)
    xLMD = np.where(low - low_1 < 0, -(low - low_1), 0)

    xPrice = xHMU - xLMD
    xPriceAbs = np.absolute(xPrice)

    xuXA = ema_vec(ema_vec(ema_vec(xPrice, r), s), u)
    xuXAAbs = ema_vec(ema_vec(ema_vec(xPriceAbs, r), s), u)

    Val1 = 100 * xuXA
    Val2 = xuXAAbs
    with np.errstate(divide='ignore', invalid='ignore'):
        dti_val = np.divide(Val1, Val2, out=np.zeros_like(Val1, dtype=float), where=Val2 != 0)

    if sequential:
        return dti_val
    else:
        return None if np.isnan(dti_val[-1]) else dti_val[-1]
