from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles

@overload
def trendflex(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def trendflex(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def trendflex(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def trendflex(candles: np.ndarray, period: int = 20, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """TrendFlex indicator by John F. Ehlers"""
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
    res = jr.trendflex(np.ascontiguousarray(source, dtype=np.float64), period)
    if sequential:
        return res
    return None if np.isnan(res[-1]) else res[-1]
