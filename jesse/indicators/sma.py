from typing import Literal, Union, overload

import numpy as np

from jesse.helpers import get_candle_source, slice_candles
from jesse_rust import sma as sma_rust, sma_last as sma_last_rust


@overload
def sma(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def sma(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def sma(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def sma(candles: np.ndarray, period: int = 5, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    SMA - Simple Moving Average

    :param candles: np.ndarray
    :param period: int - default: 5
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """

    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    if sequential:
        return sma_rust(source, period)
    # bit-for-bit identical to sma_rust(source, period)[-1], minus the
    # full-series allocation (the scalar kernel runs the same recurrence)
    return np.float64(sma_last_rust(source, period))
