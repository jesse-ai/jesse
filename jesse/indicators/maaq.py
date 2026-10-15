from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, same_length, slice_candles

@overload
def maaq(candles: np.ndarray, period: int = ..., fast_period: int = ..., slow_period: int = ..., source_type: str = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def maaq(candles: np.ndarray, period: int = ..., fast_period: int = ..., slow_period: int = ..., source_type: str = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def maaq(candles: np.ndarray, period: int = ..., fast_period: int = ..., slow_period: int = ..., source_type: str = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def maaq(candles: np.ndarray, period: int = 11, fast_period: int = 2, slow_period: int = 30, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """Moving Average Adaptive Q"""
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
    source = source[~np.isnan(source)]
    res = jr.maaq(np.ascontiguousarray(source, dtype=np.float64), period, fast_period, slow_period)
    res = same_length(candles, res)
    return res if sequential else res[-1]
