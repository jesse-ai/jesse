from collections import namedtuple
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles

DamianiVolatmeter = namedtuple("DamianiVolatmeter", ["vol", "anti"])


def damiani_volatmeter(candles, vis_atr=13, vis_std=20, sed_atr=40, sed_std=100, threshold=1.4, source_type="close", sequential=False):
    """Damiani Volatmeter"""
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
    vol, t = jr.damiani_volatmeter(
        np.ascontiguousarray(candles, dtype=np.float64),
        np.ascontiguousarray(source, dtype=np.float64),
        vis_atr, vis_std, sed_atr, sed_std, threshold,
    )
    if sequential:
        return DamianiVolatmeter(vol, t)
    return DamianiVolatmeter(vol[-1], t[-1])
