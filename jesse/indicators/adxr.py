from typing import Union

import numpy as np
from jesse.helpers import slice_candles


def adxr(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    @author KivancOzbilgic
    credits: https://www.tradingview.com/v/9f5zDi3r/
    
    ADXR - Average Directional Movement Index Rating computed manually following TradingView formula

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

    # Initialize arrays
    TR = np.zeros(n)
    DMP = np.zeros(n)
    DMM = np.zeros(n)

    # First candle, no previous data
    TR[0] = high[0] - low[0]
    DMP[0] = 0.0
    DMM[0] = 0.0

    # Calculate True Range, DMP and DMM
    for i in range(1, n):
        prev_close = close[i - 1]
        TR[i] = max(high[i] - low[i], abs(high[i] - prev_close), abs(low[i] - prev_close))
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]
        DMP[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        DMM[i] = down_move if (down_move > up_move and down_move > 0) else 0.0

    # Wilder smoothing
    STR = np.zeros(n)     # Smoothed True Range
    S_DMP = np.zeros(n)   # Smoothed DMP
    S_DMM = np.zeros(n)   # Smoothed DMM

    STR[0] = TR[0]
    S_DMP[0] = DMP[0]
    S_DMM[0] = DMM[0]
    for i in range(1, n):
        STR[i] = STR[i - 1] - (STR[i - 1] / period) + TR[i]
        S_DMP[i] = S_DMP[i - 1] - (S_DMP[i - 1] / period) + DMP[i]
        S_DMM[i] = S_DMM[i - 1] - (S_DMM[i - 1] / period) + DMM[i]

    # Calculate DI+ and DI-
    DI_plus = np.zeros(n)
    DI_minus = np.zeros(n)
    DX = np.zeros(n)
    for i in range(n):
        if STR[i] != 0:
            DI_plus[i] = (S_DMP[i] / STR[i]) * 100
            DI_minus[i] = (S_DMM[i] / STR[i]) * 100
        else:
            DI_plus[i] = 0.0
            DI_minus[i] = 0.0

        denom = DI_plus[i] + DI_minus[i]
        if denom != 0:
            DX[i] = abs(DI_plus[i] - DI_minus[i]) / denom * 100
        else:
            DX[i] = 0.0

    # Compute ADX as the simple moving average of DX
    ADX = np.full(n, np.nan)
    for i in range(period - 1, n):
        ADX[i] = np.mean(DX[i - period + 1:i + 1])

    # Compute ADXR: (current ADX + ADX from 'period' bars ago) / 2
    ADXR = np.full(n, np.nan)
    for i in range(period, n):
        ADXR[i] = (ADX[i] + ADX[i - period]) / 2

    return ADXR if sequential else ADXR[-1]
