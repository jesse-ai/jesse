from typing import Literal, Union, overload
import numpy as np
from jesse.helpers import slice_candles
from jesse_rust import atr as rust_atr, atr_last as rust_atr_last


@overload
def atr(candles: np.ndarray, period: int = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def atr(candles: np.ndarray, period: int = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def atr(candles: np.ndarray, period: int = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...


def atr(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    ATR - Average True Range using optimized Rust implementation

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    if sequential:
        return rust_atr(candles, period)
    # bit-for-bit identical to rust_atr(candles, period)[-1], minus the
    # full-series allocation (the scalar kernel runs the same recurrence)
    return np.float64(rust_atr_last(candles, period))
