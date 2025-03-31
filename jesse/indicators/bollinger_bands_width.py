from typing import Union
import numpy as np
from numba import njit
from jesse.helpers import get_candle_source, slice_candles


@njit(cache=True)
def _bb_width(source: np.ndarray, period: int, mult: float) -> np.ndarray:
    """
    Calculate Bollinger Bands Width using Numba
    """
    n = len(source)
    bbw = np.full(n, np.nan)
    
    if n < period:
        return bbw
        
    # Pre-calculate sum and sum of squares for optimization
    sum_x = np.zeros(n - period + 1)
    sum_x2 = np.zeros(n - period + 1)
    
    # Initial window
    sum_x[0] = np.sum(source[:period])
    sum_x2[0] = np.sum(source[:period] ** 2)
    
    # Rolling window calculations
    for i in range(1, n - period + 1):
        sum_x[i] = sum_x[i-1] - source[i-1] + source[i+period-1]
        sum_x2[i] = sum_x2[i-1] - source[i-1]**2 + source[i+period-1]**2
    
    # Calculate mean and standard deviation
    mean = sum_x / period
    std = np.sqrt((sum_x2 / period) - (mean ** 2))
    
    # Calculate BBW
    for i in range(period - 1, n):
        idx = i - period + 1
        basis = mean[idx]
        upper = basis + mult * std[idx]
        lower = basis - mult * std[idx]
        bbw[i] = (upper - lower) / basis
        
    return bbw


def bollinger_bands_width(candles: np.ndarray, period: int = 20, mult: float = 2.0, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    BBW - Bollinger Bands Width - Bollinger Bands Bandwidth using Numba for optimization

    :param candles: np.ndarray
    :param period: int - default: 20
    :param mult: float - default: 2
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    
    result = _bb_width(source, period, mult)
    
    return result if sequential else result[-1]
