from typing import Literal, Union, overload
import numpy as np
import jesse.helpers as jh
from jesse_rust import cvi as cvi_rust


@overload
def cvi(candles: np.ndarray, period: int = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def cvi(candles: np.ndarray, period: int = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def cvi(candles: np.ndarray, period: int = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def cvi(candles: np.ndarray, period: int = 5, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    CVI - Chaikins Volatility

    :param candles: np.ndarray
    :param period: int - default: 5
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = jh.slice_candles(candles, sequential)
    
    # Call the Rust implementation
    res = cvi_rust(candles, period)

    return jh.same_length(candles, res) if sequential else res[-1]
