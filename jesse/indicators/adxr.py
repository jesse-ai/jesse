from typing import Union

import numpy as np
from jesse.helpers import slice_candles
from numba import njit


@njit(cache=True)
def _adxr(high, low, close, period):
    n = len(high)
    TR = np.zeros(n)
    DMP = np.zeros(n)
    DMM = np.zeros(n)
    
    # First value
    TR[0] = high[0] - low[0]
    
    # Calculate TR, DMP, DMM
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i-1])
        lc = abs(low[i] - close[i-1])
        TR[i] = max(hl, hc, lc)
        
        up_move = high[i] - high[i-1]
        down_move = low[i-1] - low[i]
        
        if up_move > down_move and up_move > 0:
            DMP[i] = up_move
        else:
            DMP[i] = 0
            
        if down_move > up_move and down_move > 0:
            DMM[i] = down_move
        else:
            DMM[i] = 0
    
    # Smoothed TR, DMP, DMM
    STR = np.zeros(n)
    S_DMP = np.zeros(n)
    S_DMM = np.zeros(n)
    
    # Initialize first value
    STR[0] = TR[0]
    S_DMP[0] = DMP[0]
    S_DMM[0] = DMM[0]
    
    # Calculate smoothed values
    for i in range(1, n):
        STR[i] = STR[i-1] - (STR[i-1] / period) + TR[i]
        S_DMP[i] = S_DMP[i-1] - (S_DMP[i-1] / period) + DMP[i]
        S_DMM[i] = S_DMM[i-1] - (S_DMM[i-1] / period) + DMM[i]
    
    # Calculate DI+ and DI-
    DI_plus = np.zeros(n)
    DI_minus = np.zeros(n)
    for i in range(n):
        if STR[i] != 0:
            DI_plus[i] = (S_DMP[i] / STR[i]) * 100
            DI_minus[i] = (S_DMM[i] / STR[i]) * 100
    
    # Calculate DX
    DX = np.zeros(n)
    for i in range(n):
        denom = DI_plus[i] + DI_minus[i]
        if denom != 0:
            DX[i] = (abs(DI_plus[i] - DI_minus[i]) / denom) * 100
    
    # Calculate ADX
    ADX = np.full(n, np.nan)
    if n >= period:
        for i in range(period-1, n):
            sum_dx = 0
            for j in range(period):
                sum_dx += DX[i-j]
            ADX[i] = sum_dx / period
    
    # Calculate ADXR
    ADXR = np.full(n, np.nan)
    if n > period:
        for i in range(period, n):
            ADXR[i] = (ADX[i] + ADX[i-period]) / 2
            
    return ADXR

def adxr(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    @author KivancOzbilgic
    credits: https://www.tradingview.com/v/9f5zDi3r/
    
    ADXR - Average Directional Movement Index Rating

    :param candles: np.ndarray with at least 5 columns where index 3 is high, index 4 is low and index 2 is close
    :param period: int - period for smoothing and moving average (default: 14)
    :param sequential: bool - returns full series if True, else only the last computed value
    :return: ADXR as float or np.ndarray
    """
    candles = slice_candles(candles, sequential)
    
    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]
    
    ADXR = _adxr(high, low, close, period)
    
    return ADXR if sequential else ADXR[-1]
