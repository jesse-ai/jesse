from typing import Union

import numpy as np
from jesse.helpers import slice_candles


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
    n = len(candles)

    # Vectorized computation of True Range (TR), Directional Movement Plus (DMP) and Minus (DMM)
    TR = np.empty(n)
    DMP = np.empty(n)
    DMM = np.empty(n)
    TR[0] = high[0] - low[0]
    DMP[0] = 0.0
    DMM[0] = 0.0
    if n > 1:
        diff_high_low = high[1:] - low[1:]
        diff_high_prev_close = np.abs(high[1:] - close[:-1])
        diff_low_prev_close = np.abs(low[1:] - close[:-1])
        TR[1:] = np.maximum.reduce([diff_high_low, diff_high_prev_close, diff_low_prev_close])

        up_move = high[1:] - high[:-1]
        down_move = low[:-1] - low[1:]
        DMP[1:] = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        DMM[1:] = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # Wilder smoothing via vectorized matrix multiplication
    # The recursive formula: S[i] = S[i-1]*(1 - 1/period) + X[i] can be written in closed-form as:
    # S[i] = X[0]*(1 - 1/period)**i + sum_{j=1}^{i} X[j]*(1 - 1/period)**(i - j)
    r = 1 - 1/period
    exponents = np.subtract.outer(np.arange(n), np.arange(n))  # shape (n, n), exponents[i,j] = i - j
    weights = np.where(exponents >= 0, r ** exponents, 0.0)
    STR = weights.dot(TR)
    S_DMP = weights.dot(DMP)
    S_DMM = weights.dot(DMM)

    # Vectorized calculation of DI+ and DI-
    DI_plus = np.where(STR != 0, (S_DMP / STR) * 100, 0.0)
    DI_minus = np.where(STR != 0, (S_DMM / STR) * 100, 0.0)
    denom = DI_plus + DI_minus
    with np.errstate(divide='ignore', invalid='ignore'):
        DX = np.divide(np.abs(DI_plus - DI_minus) * 100, denom, out=np.zeros_like(denom), where=denom != 0)

    # Compute ADX as a simple moving average of DX over 'period' values using convolution
    ADX = np.full(n, np.nan)
    if n >= period:
        kernel = np.ones(period) / period
        valid_adx = np.convolve(DX, kernel, mode='valid')
        ADX[period-1:] = valid_adx

    # Compute ADXR: (current ADX + ADX from 'period' bars ago) / 2, vectorized
    ADXR = np.full(n, np.nan)
    if n > period:
        ADXR[period:] = 0.5 * (ADX[period:] + ADX[:-period])

    return ADXR if sequential else ADXR[-1]
