from typing import Union
import numpy as np
import jesse_rust as jr
from jesse.helpers import slice_candles

def sar(candles: np.ndarray, acceleration: float = 0.02, maximum: float = 0.2, sequential: bool = False) -> Union[float, np.ndarray]:
    """SAR - Parabolic SAR"""
    candles = slice_candles(candles, sequential)
    res = jr.sar(np.ascontiguousarray(candles, dtype=np.float64), acceleration, maximum)
    return res if sequential else res[-1]
