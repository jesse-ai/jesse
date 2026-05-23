from collections import namedtuple
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles

CC = namedtuple("CC", ["real", "imag", "angle", "state"])

def correlation_cycle(candles: np.ndarray, period: int = 20, threshold: int = 9, source_type: str = "close", sequential: bool = False) -> CC:
    """Correlation Cycle, Correlation Angle, Market State - John Ehlers"""
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    real, imag, angle, state = jr.correlation_cycle(np.ascontiguousarray(source, dtype=np.float64), period, float(threshold))
    if sequential:
        return CC(real, imag, angle, state)
    return CC(real[-1], imag[-1], angle[-1], state[-1])
