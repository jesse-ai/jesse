from collections import namedtuple
import numpy as np
import jesse_rust as jr
from jesse.helpers import slice_candles

HA = namedtuple("HA", ["open", "close", "high", "low"])

def heikin_ashi_candles(candles: np.ndarray, sequential: bool = False) -> HA:
    """Heikin Ashi Candles"""
    source = slice_candles(candles, sequential)
    ha_open, ha_close, ha_high, ha_low = jr.heikin_ashi_candles(np.ascontiguousarray(source, dtype=np.float64))
    if sequential:
        return HA(ha_open, ha_close, ha_high, ha_low)
    return HA(ha_open[-1], ha_close[-1], ha_high[-1], ha_low[-1])
