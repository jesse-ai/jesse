from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, same_length, slice_candles

@overload
def cg(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def cg(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def cg(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def cg(candles: np.ndarray, period: int = 10, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """Center of Gravity (CG)"""
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    res = jr.cg(np.ascontiguousarray(source, dtype=np.float64), period)
    return same_length(candles, res) if sequential else res[-1]
