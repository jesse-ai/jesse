from typing import Union
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, same_length, slice_candles

def dpo(candles: np.ndarray, period: int = 5, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """DPO - Detrended Price Oscillator"""
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    res = jr.dpo(np.ascontiguousarray(source, dtype=np.float64), period)
    return same_length(candles, res) if sequential else res[-1]
