from collections import namedtuple

from typing import Union

import numpy as np
from jesse.helpers import slice_candles
from jesse.indicators.rma import rma
from numba import njit

DX = namedtuple('DX', ['adx', 'plusDI', 'minusDI'])

@njit(cache=True)
def _fast_dm_tr(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> tuple:
    n = len(high)
    up = np.zeros(n)
    down = np.zeros(n)
    plusDM = np.zeros(n)
    minusDM = np.zeros(n)
    true_range = np.zeros(n)
    
    for i in range(n):
        if i == 0:
            up[i] = 0
            down[i] = 0
            plusDM[i] = 0
            minusDM[i] = 0
            true_range[i] = high[i] - low[i]
        else:
            up[i] = high[i] - high[i - 1]
            down[i] = low[i - 1] - low[i]
            plusDM[i] = up[i] if (up[i] > down[i] and up[i] > 0) else 0
            minusDM[i] = down[i] if (down[i] > up[i] and down[i] > 0) else 0
            a = high[i] - low[i]
            b = abs(high[i] - close[i - 1])
            c = abs(low[i] - close[i - 1])
            true_range[i] = max(a, b, c)
    
    return plusDM, minusDM, true_range

def dx(candles: np.ndarray, di_length: int = 14, adx_smoothing: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    DX - Directional Movement Index
    
    :param candles: np.ndarray
    :param di_length: int - default: 14
    :param adx_smoothing: int - default: 14
    :param sequential: bool - default: False
    
    :return: DX(adx, plusDI, minusDI)
    """
    candles = slice_candles(candles, sequential)
    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]
    
    plusDM, minusDM, true_range = _fast_dm_tr(high, low, close)
    
    tr_rma = rma(true_range, di_length, sequential=True)
    plus_rma = rma(plusDM, di_length, sequential=True)
    minus_rma = rma(minusDM, di_length, sequential=True)
    
    # Compute +DI and -DI, avoiding division by zero
    plusDI = np.where(tr_rma == 0, 0, 100 * plus_rma / tr_rma)
    minusDI = np.where(tr_rma == 0, 0, 100 * minus_rma / tr_rma)
    
    di_sum = plusDI + minusDI
    di_diff = np.abs(plusDI - minusDI)
    directional_index = di_diff / np.where(di_sum == 0, 1, di_sum)
    adx = 100 * rma(directional_index, adx_smoothing, sequential=True)
    
    if sequential:
        return DX(adx, plusDI, minusDI)
    else:
        return DX(adx[-1], plusDI[-1], minusDI[-1])
