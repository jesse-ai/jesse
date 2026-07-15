from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles

@overload
def linearreg(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def linearreg(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def linearreg(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def linearreg(candles: np.ndarray, period: int = 14, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """LINEARREG - Linear Regression"""
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
    res = jr.linearreg(np.ascontiguousarray(source, dtype=np.float64), period)
    return res if sequential else res[-1]
