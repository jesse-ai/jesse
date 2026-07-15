from typing import Literal, Union, overload
import numpy as np
import jesse_rust as jr
from jesse.helpers import get_candle_source, same_length, slice_candles

@overload
def efi(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def efi(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def efi(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def efi(candles: np.ndarray, period: int = 13, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """EFI - Elders Force Index"""
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    res = jr.efi(
        np.ascontiguousarray(source, dtype=np.float64),
        np.ascontiguousarray(candles, dtype=np.float64),
        period
    )
    res_with_nan = same_length(candles, res)
    return res_with_nan if sequential else res_with_nan[-1]
