from typing import Union

from numba import njit
import numpy as np
from jesse.helpers import get_candle_source, slice_candles


def t3(candles: np.ndarray, period: int = 5, vfactor: float = 0, source_type: str = "close",
       sequential: bool = False) -> Union[float, np.ndarray]:
    """
    T3 - Triple Exponential Moving Average (T3)
    
    The T3 moving average is a type of moving average that uses the DEMA (Double Exponential Moving Average) 
    calculations multiple times with a volume factor weighting.
    
    :param candles: np.ndarray
    :param period: int - default: 5
    :param vfactor: float - default: 0
    :param source_type: str - default: "close"
    :param sequential: bool - default: False
    
    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
        
    # Calculate k based on volume factor
    k = 2 / (period + 1)
    
    # Calculate weights based on volume factor
    w1 = -vfactor ** 3
    w2 = 3 * vfactor ** 2 + 3 * vfactor ** 3
    w3 = -6 * vfactor ** 2 - 3 * vfactor - 3 * vfactor ** 3
    w4 = 1 + 3 * vfactor + vfactor ** 3 + 3 * vfactor ** 2
    

    # Calculate six EMAs in sequence
    e1 = _ema(source, k)
    e2 = _ema(e1, k)
    e3 = _ema(e2, k)
    e4 = _ema(e3, k)
    e5 = _ema(e4, k)
    e6 = _ema(e5, k)
    
    # Calculate T3 using the weighted sum of EMAs
    t3 = w1 * e6 + w2 * e5 + w3 * e4 + w4 * e3
    
    return t3 if sequential else t3[-1]


@njit
def _ema_loop(data: np.ndarray, alpha: float, alpha_rev: float, result: np.ndarray) -> np.ndarray:
    for i in range(1, len(data)):
        result[i] = alpha * data[i] + alpha_rev * result[i-1]
    return result


@njit
def _ema(data: np.ndarray, alpha: float) -> np.ndarray:
    alpha_rev = 1 - alpha
    n = data.shape[0]
    
    # Initialize with first value
    result = np.empty(n)
    result[0] = data[0]
    
    # Call the optimized loop function
    return _ema_loop(data, alpha, alpha_rev, result)
    