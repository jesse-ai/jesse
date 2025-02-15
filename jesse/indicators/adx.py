from typing import Union
import numpy as np
from numba import njit
from jesse.helpers import slice_candles


@njit
def _wilder_smooth(arr: np.ndarray, period: int) -> np.ndarray:
    """
    Wilder's smoothing helper function
    """
    n = len(arr)
    result = np.full(n, np.nan)
    # First value is sum of first "period" values
    result[period] = np.sum(arr[1:period + 1])
    # Apply smoothing formula
    for i in range(period + 1, n):
        result[i] = result[i - 1] - (result[i - 1] / period) + arr[i]
    return result


@njit
def _calculate_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """
    Core ADX calculation using Numba
    """
    n = len(close)
    TR = np.zeros(n)
    plusDM = np.zeros(n)
    minusDM = np.zeros(n)

    # Calculate True Range and Directional Movement
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i-1])
        lc = abs(low[i] - close[i-1])
        TR[i] = max(max(hl, hc), lc)

        h_diff = high[i] - high[i-1]
        l_diff = low[i-1] - low[i]

        if h_diff > l_diff and h_diff > 0:
            plusDM[i] = h_diff
        else:
            plusDM[i] = 0

        if l_diff > h_diff and l_diff > 0:
            minusDM[i] = l_diff
        else:
            minusDM[i] = 0

    # Smooth the TR and DM values
    tr_smooth = _wilder_smooth(TR, period)
    plus_dm_smooth = _wilder_smooth(plusDM, period)
    minus_dm_smooth = _wilder_smooth(minusDM, period)

    # Calculate DI+ and DI-
    DI_plus = np.full(n, np.nan)
    DI_minus = np.full(n, np.nan)
    DX = np.full(n, np.nan)

    for i in range(period, n):
        if tr_smooth[i] != 0:
            DI_plus[i] = 100 * plus_dm_smooth[i] / tr_smooth[i]
            DI_minus[i] = 100 * minus_dm_smooth[i] / tr_smooth[i]
            
            if (DI_plus[i] + DI_minus[i]) != 0:
                DX[i] = 100 * abs(DI_plus[i] - DI_minus[i]) / (DI_plus[i] + DI_minus[i])
            else:
                DX[i] = 0
        else:
            DI_plus[i] = 0
            DI_minus[i] = 0
            DX[i] = 0

    # Calculate ADX
    ADX = np.full(n, np.nan)
    start_index = period * 2

    if start_index < n:
        # Calculate first ADX value
        ADX[start_index] = np.mean(DX[period:start_index])
        
        # Calculate subsequent ADX values
        for i in range(start_index + 1, n):
            ADX[i] = (ADX[i-1] * (period - 1) + DX[i]) / period

    return ADX


def adx(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    ADX - Average Directional Movement Index using Numba for optimization.

    :param candles: np.ndarray, expected 2D array with OHLCV data where index 3 is high, index 4 is low, and index 2 is close
    :param period: int - default: 14
    :param sequential: bool - if True, return full series, else return last value
    :return: float | np.ndarray
    """
    if len(candles.shape) < 2:
        raise ValueError("adx indicator requires a 2D array of candles")
    
    candles = slice_candles(candles, sequential)

    if len(candles) <= period:
        return np.nan if sequential else np.nan

    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]

    result = _calculate_adx(high, low, close, period)

    return result if sequential else result[-1]
