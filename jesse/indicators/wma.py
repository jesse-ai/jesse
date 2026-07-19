from typing import Literal, Union, overload

import numpy as np

from jesse.helpers import get_candle_source, slice_candles
from jesse_rust import wma as wma_rust


@overload
def wma(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def wma(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def wma(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def wma(candles: np.ndarray, period: int = 30, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    WMA - Weighted Moving Average

    :param candles: np.ndarray
    :param period: int - default: 30
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    # Convert to float64 for Rust compatibility
    source_f64 = np.asarray(source, dtype=np.float64)
    
    # Call the Rust implementation
    result = wma_rust(source_f64, period)
    
    return result if sequential else result[-1]
