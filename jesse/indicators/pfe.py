from typing import Union
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, same_length, slice_candles

def pfe(candles: np.ndarray, period: int = 10, smoothing: int = 5, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """Polarized Fractal Efficiency (PFE)"""
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    res = jr.pfe(np.ascontiguousarray(source, dtype=np.float64), period, smoothing)
    return res if sequential else res[-1]
