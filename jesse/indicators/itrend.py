from collections import namedtuple
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles

ITREND = namedtuple("ITREND", ["signal", "it", "trigger"])

def itrend(candles: np.ndarray, alpha: float = 0.07, source_type: str = "hl2", sequential: bool = False) -> ITREND:
    """Instantaneous Trendline"""
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    signal, it, trigger = jr.itrend(np.ascontiguousarray(source, dtype=np.float64), alpha)
    if sequential:
        return ITREND(signal, it, trigger)
    return ITREND(signal[-1], it[-1], trigger[-1])
