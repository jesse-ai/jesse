from collections import namedtuple
import numpy as np
import jesse_rust as jr
from jesse.helpers import slice_candles

EMD = namedtuple("EMD", ["upperband", "middleband", "lowerband"])

def emd(candles: np.ndarray, period: int = 20, delta: float = 0.5, fraction: float = 0.1, sequential: bool = False) -> EMD:
    """Empirical Mode Decomposition by John F. Ehlers and Ric Way"""
    candles = slice_candles(candles, sequential)
    upper, middle, lower = jr.emd(np.ascontiguousarray(candles, dtype=np.float64), period, delta, fraction)
    if sequential:
        return EMD(upper, middle, lower)
    return EMD(upper[-1], middle[-1], lower[-1])
