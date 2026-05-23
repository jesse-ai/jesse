from typing import Union
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, same_length, slice_candles

def hwma(candles: np.ndarray, na: float = 0.2, nb: float = 0.1, nc: float = 0.1, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """Holt-Winter Moving Average"""
    if not ((0 < na < 1) or (0 < nb < 1) or (0 < nc < 1)):
        raise ValueError("Bad parameters. They have to be: 0 < na nb nc < 1")
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
    source_clean = source[~np.isnan(source)]
    res = jr.hwma(np.ascontiguousarray(source_clean, dtype=np.float64), na, nb, nc)
    res = same_length(candles, res)
    return res if sequential else res[-1]
