from typing import Union
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, same_length, slice_candles

def maaq(candles: np.ndarray, period: int = 11, fast_period: int = 2, slow_period: int = 30, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """Moving Average Adaptive Q"""
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
    source = source[~np.isnan(source)]
    res = jr.maaq(np.ascontiguousarray(source, dtype=np.float64), period, fast_period, slow_period)
    res = same_length(candles, res)
    return res if sequential else res[-1]
