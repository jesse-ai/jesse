from typing import Union
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles

def dema(candles: np.ndarray, period: int = 30, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """DEMA - Double Exponential Moving Average"""
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
    source_f64 = np.asarray(source, dtype=np.float64)
    result = jr.dema(source_f64, period)
    return result if sequential else result[-1]
