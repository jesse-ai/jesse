from collections import namedtuple
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles

VossFilter = namedtuple("VossFilter", ["voss", "filt"])

def voss(candles: np.ndarray, period: int = 20, predict: int = 3, bandwith: float = 0.25, source_type: str = "close", sequential: bool = False) -> VossFilter:
    """Voss Predictive Filter by John F. Ehlers"""
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    voss_v, filt = jr.voss(np.ascontiguousarray(source, dtype=np.float64), period, predict, bandwith)
    if sequential:
        return VossFilter(voss_v, filt)
    return VossFilter(voss_v[-1], filt[-1])
