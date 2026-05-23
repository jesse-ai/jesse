from collections import namedtuple
import numpy as np
import jesse_rust as jr
from jesse.helpers import slice_candles

SuperTrend = namedtuple("SuperTrend", ["trend", "changed"])

def supertrend(candles: np.ndarray, period: int = 10, factor: float = 3, sequential: bool = False) -> SuperTrend:
    """SuperTrend indicator"""
    candles = slice_candles(candles, sequential)
    trend, changed = jr.supertrend(np.ascontiguousarray(candles, dtype=np.float64), period, factor)
    if sequential:
        return SuperTrend(trend, changed)
    return SuperTrend(trend[-1], changed[-1])
