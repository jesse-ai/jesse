from collections import namedtuple
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles

MAMA = namedtuple("MAMA", ["mama", "fama"])

def mama(candles: np.ndarray, fastlimit: float = 0.5, slowlimit: float = 0.05, source_type: str = "close", sequential: bool = False) -> MAMA:
    """MAMA - MESA Adaptive Moving Average"""
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
    mama_v, fama_v = jr.mama(np.ascontiguousarray(source, dtype=np.float64), fastlimit, slowlimit)
    if sequential:
        return MAMA(mama_v, fama_v)
    return MAMA(mama_v[-1], fama_v[-1])
