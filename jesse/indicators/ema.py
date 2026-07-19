from typing import Literal, Union, overload

import numpy as np

from jesse.helpers import get_candle_source, slice_candles
from jesse_rust import ema as ema_rust, ema_last as ema_last_rust


@overload
def ema(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def ema(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def ema(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...


def ema(candles: np.ndarray, period: int = 5, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    EMA - Exponential Moving Average

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
        return ema_rust(source, period)
    # bit-for-bit identical to ema_rust(source, period)[-1], minus the
    # full-series allocation (the scalar kernel runs the same recurrence)
    return np.float64(ema_last_rust(source, period))
