from typing import Union
import numpy as np
import jesse_rust as jr
from jesse.helpers import slice_candles

def aroonosc(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """AROONOSC - Aroon Oscillator"""
    candles = slice_candles(candles, sequential)
    res = jr.aroonosc(np.ascontiguousarray(candles, dtype=np.float64), period)
    return res if sequential else res[-1]
