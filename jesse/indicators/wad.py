from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import same_length, slice_candles

@overload
def wad(candles: np.ndarray, sequential: Literal[False] = ...) -> float: ...
@overload
def wad(candles: np.ndarray, sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def wad(candles: np.ndarray, sequential: bool = ...) -> Union[float, np.ndarray]: ...

def wad(candles: np.ndarray, sequential: bool = False) -> Union[float, np.ndarray]:
    """WAD - Williams Accumulation/Distribution"""
    candles = slice_candles(candles, sequential)
    res = jr.wad(np.ascontiguousarray(candles, dtype=np.float64))
    return same_length(candles, res) if sequential else res[-1]
