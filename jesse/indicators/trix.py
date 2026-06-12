from typing import Union
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles

def trix(candles: np.ndarray, period: int = 18, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """TRIX - 1-day Rate-Of-Change of a Triple Smooth EMA"""
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    res = jr.trix(np.ascontiguousarray(source, dtype=np.float64), period)
    return res if sequential else res[-1]
