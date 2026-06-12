from collections import namedtuple
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles

BandPass = namedtuple("BandPass", ["bp", "bp_normalized", "signal", "trigger"])

def bandpass(candles: np.ndarray, period: int = 20, bandwidth: float = 0.3, source_type: str = "close", sequential: bool = False) -> BandPass:
    """BandPass Filter"""
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    bp, bp_norm, signal, trigger = jr.bandpass(np.ascontiguousarray(source, dtype=np.float64), period, bandwidth)
    if sequential:
        return BandPass(bp, bp_norm, signal, trigger)
    return BandPass(bp[-1], bp_norm[-1], signal[-1], trigger[-1])
