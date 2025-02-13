from typing import Union
import numpy as np
from numba import njit
from jesse.helpers import slice_candles


@njit
def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """
    Calculate ATR using Numba
    """
    n = len(close)
    tr = np.empty(n)
    atr_values = np.full(n, np.nan)
    
    # Calculate True Range
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i-1])
        lc = abs(low[i] - close[i-1])
        tr[i] = max(max(hl, hc), lc)
    
    if n < period:
        return atr_values
        
    # First ATR value is the simple average of the first 'period' true ranges
    atr_values[period-1] = np.mean(tr[:period])
    
    # Calculate subsequent ATR values using Wilder's smoothing
    for i in range(period, n):
        atr_values[i] = (atr_values[i-1] * (period - 1) + tr[i]) / period
        
    return atr_values


def atr(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    ATR - Average True Range using Numba for optimization

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]

    result = _atr(high, low, close, period)
    
    return result if sequential else result[-1]
