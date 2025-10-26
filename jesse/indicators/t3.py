from typing import Union

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
    # Check if jesse_rust is available
    try:
        import jesse_rust
        
        if len(candles.shape) == 1:
            # Handle case where source array is passed directly
            # Convert to candles format for Rust function
            mock_candles = np.zeros((len(candles), 6))
            mock_candles[:, 2] = candles  # Put source in close column
            result = jesse_rust.t3(mock_candles, period, vfactor, "close", sequential)
        else:
            candles = slice_candles(candles, sequential)
            result = jesse_rust.t3(candles, period, vfactor, source_type, sequential)
        
        return result if sequential else result[-1]
        
    except ImportError:
        # Fallback to pure Python implementation
        if len(candles.shape) == 1:
            source = candles
        else:
            candles = slice_candles(candles, sequential)
            source = get_candle_source(candles, source_type=source_type)
            
        k = 2 / (period + 1)
        
        # Calculate weights based on volume factor
        w1 = -vfactor ** 3
        w2 = 3 * vfactor ** 2 + 3 * vfactor ** 3
        w3 = -6 * vfactor ** 2 - 3 * vfactor - 3 * vfactor ** 3
        w4 = 1 + 3 * vfactor + vfactor ** 3 + 3 * vfactor ** 2
        
        t3 = _t3_fast_python(source, k, w1, w2, w3, w4)
        
        return t3 if sequential else t3[-1]


def _t3_fast_python(source: np.ndarray, k: float, w1: float, w2: float, w3: float, w4: float) -> np.ndarray:
    """
    Pure Python implementation of T3 calculation
    """
    n = len(source)
    e1 = np.zeros(n)
    e2 = np.zeros(n)
    e3 = np.zeros(n)
    e4 = np.zeros(n)
    e5 = np.zeros(n)
    e6 = np.zeros(n)
    t3 = np.zeros(n)
    
    # Initialize first values
    e1[0] = source[0]
    e2[0] = e1[0]
    e3[0] = e2[0]
    e4[0] = e3[0]
    e5[0] = e4[0]
    e6[0] = e5[0]
    
    k_rev = 1 - k
    
    # Calculate all EMAs in a single loop for better cache utilization
    for i in range(1, n):
        e1[i] = k * source[i] + k_rev * e1[i-1]
        e2[i] = k * e1[i] + k_rev * e2[i-1]
        e3[i] = k * e2[i] + k_rev * e3[i-1]
        e4[i] = k * e3[i] + k_rev * e4[i-1]
        e5[i] = k * e4[i] + k_rev * e5[i-1]
        e6[i] = k * e5[i] + k_rev * e6[i-1]
        t3[i] = w1 * e6[i] + w2 * e5[i] + w3 * e4[i] + w4 * e3[i]
    
    return t3