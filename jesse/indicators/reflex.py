from typing import Union
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles

def reflex(candles: np.ndarray, period: int = 20, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """Reflex indicator by John F. Ehlers"""
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
    res = jr.reflex(np.ascontiguousarray(source, dtype=np.float64), period)
    if sequential:
        return res
    return None if np.isnan(res[-1]) else res[-1]
