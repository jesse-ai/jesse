from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, slice_candles

@overload
def jma(candles: np.ndarray, period: int = ..., phase: float = ..., power: int = ..., source_type: str = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def jma(candles: np.ndarray, period: int = ..., phase: float = ..., power: int = ..., source_type: str = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def jma(candles: np.ndarray, period: int = ..., phase: float = ..., power: int = ..., source_type: str = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def jma(candles: np.ndarray, period: int = 7, phase: float = 50, power: int = 2, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """Jurik Moving Average"""
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
    res = jr.jma(np.ascontiguousarray(source, dtype=np.float64), period, phase, power)
    return res if sequential else res[-1]
