from typing import Union
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles

def mcginley_dynamic(candles: np.ndarray, period: int = 10, k: float = 0.6, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """McGinley Dynamic"""
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
    res = jr.mcginley_dynamic(np.ascontiguousarray(source, dtype=np.float64), period, k)
    return res if sequential else res[-1]
