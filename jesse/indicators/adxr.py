from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import slice_candles

@overload
def adxr(candles: np.ndarray, period: int = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def adxr(candles: np.ndarray, period: int = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def adxr(candles: np.ndarray, period: int = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def adxr(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """ADXR - Average Directional Movement Index Rating"""
    candles = slice_candles(candles, sequential)
    res = jr.adxr(np.ascontiguousarray(candles, dtype=np.float64), period)
    return res if sequential else res[-1]
