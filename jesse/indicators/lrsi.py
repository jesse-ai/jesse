from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import slice_candles

@overload
def lrsi(candles: np.ndarray, alpha: float = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def lrsi(candles: np.ndarray, alpha: float = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def lrsi(candles: np.ndarray, alpha: float = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def lrsi(candles: np.ndarray, alpha: float = 0.2, sequential: bool = False) -> Union[float, np.ndarray]:
    """RSI Laguerre Filter"""
    candles = slice_candles(candles, sequential)
    res = jr.lrsi(np.ascontiguousarray(candles, dtype=np.float64), alpha)
    if sequential:
        return res
    return None if np.isnan(res[-1]) else res[-1]
