from typing import Union
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles

def cfo(candles: np.ndarray, period: int = 14, scalar: float = 100, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """CFO - Chande Forecast Oscillator"""
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    res = jr.cfo(np.ascontiguousarray(source, dtype=np.float64), period, scalar)
    if sequential:
        return res
    return None if np.isnan(res[-1]) else res[-1]
