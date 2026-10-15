from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import same_length, slice_candles

@overload
def qstick(candles: np.ndarray, period: int = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def qstick(candles: np.ndarray, period: int = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def qstick(candles: np.ndarray, period: int = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def qstick(candles: np.ndarray, period: int = 5, sequential: bool = False) -> Union[float, np.ndarray]:
    """QStick - Moving average of (close - open)"""
    candles = slice_candles(candles, sequential)
    res = jr.qstick(np.ascontiguousarray(candles, dtype=np.float64), period)
    return same_length(candles, res) if sequential else res[-1]
