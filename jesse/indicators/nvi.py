from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, same_length, slice_candles

@overload
def nvi(candles: np.ndarray, source_type: str = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def nvi(candles: np.ndarray, source_type: str = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def nvi(candles: np.ndarray, source_type: str = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def nvi(candles: np.ndarray, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """NVI - Negative Volume Index"""
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    res = jr.nvi(
        np.ascontiguousarray(source, dtype=np.float64),
        np.ascontiguousarray(candles, dtype=np.float64)
    )
    return same_length(candles, res) if sequential else res[-1]
