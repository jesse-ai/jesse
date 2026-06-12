from collections import namedtuple
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles

PMA = namedtuple("PMA", ["predict", "trigger"])

def pma(candles: np.ndarray, source_type: str = "hl2", sequential: bool = False) -> PMA:
    """Ehlers Predictive Moving Average"""
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
    predict, trigger = jr.pma(np.ascontiguousarray(source, dtype=np.float64))
    if sequential:
        return PMA(predict, trigger)
    return PMA(predict[-1], trigger[-1])
