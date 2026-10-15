from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import slice_candles

@overload
def dti(candles: np.ndarray, r: int = ..., s: int = ..., u: int = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def dti(candles: np.ndarray, r: int = ..., s: int = ..., u: int = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def dti(candles: np.ndarray, r: int = ..., s: int = ..., u: int = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def dti(candles: np.ndarray, r: int = 14, s: int = 10, u: int = 5, sequential: bool = False) -> Union[float, np.ndarray]:
    """DTI by William Blau"""
    candles = slice_candles(candles, sequential)
    res = jr.dti(candles, r, s, u)
    if sequential:
        return res
    return None if np.isnan(res[-1]) else res[-1]
