from typing import Union

import numpy as np
try:
    from numba import njit
except ImportError:
    njit = lambda a : a

from jesse.helpers import get_candle_source, slice_candles


def jma(candles: np.ndarray, period:int=7, phase:float=50, power:int=2, source_type:str='close', sequential:bool=False) -> Union[
  float, np.ndarray]:
    """
    Jurik Moving Average
    Port of: https://tradingview.com/script/nZuBWW9j-Jurik-Moving-Average/
    """

    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    phaseRatio = 0.5 if phase < -100 else (2.5 if phase > 100 else phase / 100 + 1.5)
    beta = 0.45 * (period - 1) / (0.45 * (period - 1) + 2)
    alpha = pow(beta, power)

    res = jma_helper(source, phaseRatio, beta, alpha)

    return res if sequential else res[-1]


@njit
def jma_helper(src, phaseRatio, beta, alpha):
    jma = np.copy(src)

    e0 = np.full_like(src, 0)
    e1 = np.full_like(src, 0)
    e2 = np.full_like(src, 0)

    for i in range(1, src.shape[0]):
      e0[i] = (1 - alpha) * src[i] + alpha * e0[i-1]
      e1[i] = (src[i] - e0[i]) * (1 - beta) + beta * e1[i-1]
      e2[i] = (e0[i] + phaseRatio * e1[i] - jma[i-1]) * pow(1 - alpha, 2) + pow(alpha, 2) * e2[i-1]
      jma[i] = e2[i] + jma[i-1]

    return jma
