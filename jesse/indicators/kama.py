from typing import Union
import numpy as np
from numba import njit
from jesse.helpers import get_candle_source, slice_candles


@njit(cache=True)
def _calculate_kama(src: np.ndarray, period: int, fast_length: int, slow_length: int) -> np.ndarray:
    """
    Core KAMA calculation using Numba
    """
    n = len(src)
    result = np.empty(n, dtype=np.float64)
    result[:period] = src[:period]  # First 'period' values are same as source
    
    if n <= period:
        return result
        
    # Calculate the efficiency ratio multiplier
    fast_alpha = 2.0 / (fast_length + 1)
    slow_alpha = 2.0 / (slow_length + 1)
    alpha_diff = fast_alpha - slow_alpha

    # Start the calculation after the initial period
    for i in range(period, n):
        # Calculate Efficiency Ratio
        change = abs(src[i] - src[i - period])
        volatility = 0.0
        for j in range(i - period + 1, i + 1):
            volatility += abs(src[j] - src[j - 1])
            
        er = change / volatility if volatility != 0 else 0.0
        
        # Calculate smoothing constant
        sc = (er * alpha_diff + slow_alpha) ** 2
        
        # Calculate KAMA
        result[i] = result[i - 1] + sc * (src[i] - result[i - 1])
        
    return result


def kama(candles: np.ndarray, period: int = 14, fast_length: int = 2, slow_length: int = 30, 
         source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    KAMA - Kaufman Adaptive Moving Average using Numba for optimization
    
    :param candles: np.ndarray
    :param period: int - default: 14, lookback period for the calculation
    :param fast_length: int - default: 2, fast EMA length for smoothing factor
    :param slow_length: int - default: 30, slow EMA length for smoothing factor
    :param source_type: str - default: "close", specifies the candle field
    :param sequential: bool - default: False, if True returns the full array, otherwise only the last value

    :return: float | np.ndarray
    """
    if candles.ndim == 1:
        src = candles
    else:
        candles = slice_candles(candles, sequential)
        src = get_candle_source(candles, source_type=source_type)

    src = np.asarray(src, dtype=np.float64)
    
    result = _calculate_kama(src, period, fast_length, slow_length)
    
    return result if sequential else result[-1]
