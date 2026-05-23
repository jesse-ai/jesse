from collections import namedtuple
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles
from jesse.indicators.ma import ma

KeltnerChannel = namedtuple("KeltnerChannel", ["upperband", "middleband", "lowerband"])


def keltner(candles: np.ndarray, period: int = 20, multiplier: float = 2, matype: int = 1,
            source_type: str = "close", sequential: bool = False) -> KeltnerChannel:
    """Keltner Channels"""
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    if matype == 24 or matype == 29:
        ma_values = ma(candles, period=period, matype=matype, source_type=source_type, sequential=True)
    else:
        ma_values = ma(source, period=period, matype=matype, sequential=True)
    up, mid, low = jr.keltner_inner(
        np.ascontiguousarray(ma_values, dtype=np.float64),
        np.ascontiguousarray(candles[:, 3], dtype=np.float64),
        np.ascontiguousarray(candles[:, 4], dtype=np.float64),
        np.ascontiguousarray(candles[:, 2], dtype=np.float64),
        period, multiplier
    )
    if sequential:
        return KeltnerChannel(up, mid, low)
    return KeltnerChannel(up[-1], mid[-1], low[-1])
