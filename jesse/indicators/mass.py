from typing import Union
import numpy as np
import jesse_rust as jr
from jesse.helpers import same_length, slice_candles

def mass(candles: np.ndarray, period: int = 5, sequential: bool = False) -> Union[float, np.ndarray]:
    """MASS - Mass Index"""
    candles = slice_candles(candles, sequential)
    res = jr.mass(np.ascontiguousarray(candles, dtype=np.float64), period)
    return same_length(candles, res) if sequential else res[-1]
