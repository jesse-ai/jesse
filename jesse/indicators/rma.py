from typing import Union
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles

def rma(candles: np.ndarray, length: int = 14, source_type="close", sequential=False) -> Union[float, np.ndarray]:
    """Moving average used in RSI. Exponentially weighted with alpha = 1/length."""
    if length < 1:
        raise ValueError("Bad parameters.")
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
    res = jr.rma(np.ascontiguousarray(source, dtype=np.float64), length)
    return res if sequential else res[-1]
