from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles

@overload
def high_pass_2_pole(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def high_pass_2_pole(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def high_pass_2_pole(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def high_pass_2_pole(candles: np.ndarray, period: int = 48, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """(2 pole) high-pass filter by John F. Ehlers"""
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
    res = jr.high_pass_2_pole(np.ascontiguousarray(source, dtype=np.float64), period)
    if sequential:
        return res
    return None if np.isnan(res[-1]) else res[-1]


def high_pass_2_pole_fast(source, period):
    """Internal helper for dec_osc, decycler, roofing."""
    return jr.high_pass_2_pole(np.ascontiguousarray(source, dtype=np.float64), int(period))
