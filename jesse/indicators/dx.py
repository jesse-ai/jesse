from collections import namedtuple
from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import slice_candles

DX = namedtuple("DX", ["adx", "plusDI", "minusDI"])

@overload
def dx(candles: np.ndarray, di_length: int = ..., adx_smoothing: int = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def dx(candles: np.ndarray, di_length: int = ..., adx_smoothing: int = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def dx(candles: np.ndarray, di_length: int = ..., adx_smoothing: int = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def dx(candles: np.ndarray, di_length: int = 14, adx_smoothing: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """DX - Directional Movement Index"""
    candles = slice_candles(candles, sequential)
    adx, plusDI, minusDI = jr.dx(np.ascontiguousarray(candles, dtype=np.float64), di_length, adx_smoothing, sequential)
    if sequential:
        return DX(adx, plusDI, minusDI)
    return DX(adx[-1], plusDI[-1], minusDI[-1])
