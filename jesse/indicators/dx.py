from collections import namedtuple

from typing import Union

import numpy as np
from jesse.helpers import slice_candles
from numba import njit

DX = namedtuple('DX', ['adx', 'plusDI', 'minusDI'])

@njit(cache=True)
def _rma(src, length):
    alpha = 1.0 / length
    output = np.zeros_like(src)
    output[0] = src[0]
    for i in range(1, len(src)):
        output[i] = alpha * src[i] + (1 - alpha) * output[i-1]
    return output

@njit(cache=True)
def _dx(high, low, close, di_length, adx_smoothing):
    n = len(high)
    
    # Pre-allocate arrays
    plusDM = np.zeros(n)
    minusDM = np.zeros(n)
    tr = np.zeros(n)
    
    # Calculate True Range and Directional Movement
    for i in range(1, n):
        high_diff = high[i] - high[i-1]
        low_diff = low[i-1] - low[i]
        
        # +DM
        if high_diff > low_diff and high_diff > 0:
            plusDM[i] = high_diff
        
        # -DM
        if low_diff > high_diff and low_diff > 0:
            minusDM[i] = low_diff
            
        # True Range
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i-1]),
            abs(low[i] - close[i-1])
        )
    
    # Calculate smoothed values
    tr_rma = _rma(tr, di_length)
    plus_rma = _rma(plusDM, di_length)
    minus_rma = _rma(minusDM, di_length)
    
    # Calculate +DI and -DI
    plusDI = np.zeros(n)
    minusDI = np.zeros(n)
    
    for i in range(n):
        if tr_rma[i] != 0:
            plusDI[i] = 100 * plus_rma[i] / tr_rma[i]
            minusDI[i] = 100 * minus_rma[i] / tr_rma[i]
    
    # Calculate DX
    dx_values = np.zeros(n)
    for i in range(n):
        di_sum = plusDI[i] + minusDI[i]
        if di_sum != 0:
            dx_values[i] = 100 * abs(plusDI[i] - minusDI[i]) / di_sum
    
    # Calculate ADX
    adx = _rma(dx_values, adx_smoothing)
    
    return adx, plusDI, minusDI

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
    
    adx, plusDI, minusDI = _dx(
        candles[:, 3],  # high
        candles[:, 4],  # low
        candles[:, 2],  # close
        di_length,
        adx_smoothing
    )
    
    if sequential:
        return DX(adx, plusDI, minusDI)
    else:
        return DX(adx[-1], plusDI[-1], minusDI[-1])
