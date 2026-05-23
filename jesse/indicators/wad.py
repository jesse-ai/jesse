from typing import Union
import numpy as np
import jesse_rust as jr
from jesse.helpers import same_length, slice_candles

def wad(candles: np.ndarray, sequential: bool = False) -> Union[float, np.ndarray]:
    """WAD - Williams Accumulation/Distribution"""
    candles = slice_candles(candles, sequential)
    res = jr.wad(np.ascontiguousarray(candles, dtype=np.float64))
    return same_length(candles, res) if sequential else res[-1]
