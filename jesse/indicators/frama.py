from typing import Union
import numpy as np
import jesse_rust as jr
from jesse.helpers import slice_candles

def frama(candles: np.ndarray, window: int = 10, FC: int = 1, SC: int = 300, sequential: bool = False) -> Union[float, np.ndarray]:
    """Fractal Adaptive Moving Average (FRAMA)"""
    candles = slice_candles(candles, sequential)
    n = window
    if n % 2 == 1:
        print("FRAMA n must be even. Adding one")
        n += 1
    res = jr.frama(np.ascontiguousarray(candles, dtype=np.float64), n, FC, SC)
    if sequential:
        return res
    return res[-1]
