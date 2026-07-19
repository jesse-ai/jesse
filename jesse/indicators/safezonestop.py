from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import slice_candles

@overload
def safezonestop(candles: np.ndarray, period: int = ..., mult: float = ..., max_lookback: int = ..., direction: str = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def safezonestop(candles: np.ndarray, period: int = ..., mult: float = ..., max_lookback: int = ..., direction: str = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def safezonestop(candles: np.ndarray, period: int = ..., mult: float = ..., max_lookback: int = ..., direction: str = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def safezonestop(candles: np.ndarray, period: int = 22, mult: float = 2.5, max_lookback: int = 3, direction: str = "long", sequential: bool = False) -> Union[float, np.ndarray]:
    """Safezone Stops"""
    candles = slice_candles(candles, sequential)
    is_long = direction == "long"
    res = jr.safezonestop(np.ascontiguousarray(candles, dtype=np.float64), period, mult, max_lookback, is_long)
    return res if sequential else res[-1]
