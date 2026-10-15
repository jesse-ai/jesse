from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, same_length, slice_candles

@overload
def vidya(candles: np.ndarray, length: int = ..., fix_cmo: bool = ..., select: bool = ..., source_type: str = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def vidya(candles: np.ndarray, length: int = ..., fix_cmo: bool = ..., select: bool = ..., source_type: str = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def vidya(candles: np.ndarray, length: int = ..., fix_cmo: bool = ..., select: bool = ..., source_type: str = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def vidya(candles: np.ndarray, length: int = 9, fix_cmo: bool = True, select: bool = True, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """VIDYA - Variable Index Dynamic Average"""
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
    res = jr.vidya(np.ascontiguousarray(source, dtype=np.float64), length, fix_cmo, select)
    return same_length(candles, res) if sequential else res[-1]
