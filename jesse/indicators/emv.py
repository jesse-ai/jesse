from typing import Union
import numpy as np
import jesse_rust as jr
from jesse.helpers import same_length, slice_candles

def emv(candles: np.ndarray, length: int = 14, div: int = 10000, sequential: bool = False) -> Union[float, np.ndarray]:
    """EMV - Ease of Movement"""
    candles = slice_candles(candles, sequential)
    res = jr.emv(np.ascontiguousarray(candles, dtype=np.float64), length, float(div))
    return same_length(candles, res) if sequential else res[-1]
