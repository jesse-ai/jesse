from typing import Union
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles

def cmo(candles: np.ndarray, period: int = 14, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """CMO - Chande Momentum Oscillator"""
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    res = jr.cmo(np.ascontiguousarray(source, dtype=np.float64), period)
    return res if sequential else res[-1]
