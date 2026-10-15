from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import slice_candles

@overload
def sar(candles: np.ndarray, acceleration: float = ..., maximum: float = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def sar(candles: np.ndarray, acceleration: float = ..., maximum: float = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def sar(candles: np.ndarray, acceleration: float = ..., maximum: float = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def sar(candles: np.ndarray, acceleration: float = 0.02, maximum: float = 0.2, sequential: bool = False) -> Union[float, np.ndarray]:
    """SAR - Parabolic SAR"""
    candles = slice_candles(candles, sequential)
    res = jr.sar(np.ascontiguousarray(candles, dtype=np.float64), acceleration, maximum)
    return res if sequential else res[-1]
