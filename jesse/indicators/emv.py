from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import same_length, slice_candles

@overload
def emv(candles: np.ndarray, length: int = ..., div: int = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def emv(candles: np.ndarray, length: int = ..., div: int = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def emv(candles: np.ndarray, length: int = ..., div: int = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def emv(candles: np.ndarray, length: int = 14, div: int = 10000, sequential: bool = False) -> Union[float, np.ndarray]:
    """EMV - Ease of Movement"""
    candles = slice_candles(candles, sequential)
    res = jr.emv(np.ascontiguousarray(candles, dtype=np.float64), length, float(div))
    return same_length(candles, res) if sequential else res[-1]
