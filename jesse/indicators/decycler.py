from typing import Literal, Union, overload

import numpy as np

from jesse.helpers import get_candle_source, slice_candles

from .high_pass_2_pole import high_pass_2_pole_fast


@overload
def decycler(candles: np.ndarray, hp_period: int = ..., source_type: str = ..., sequential: Literal[False] = ...) -> float: ...
@overload
def decycler(candles: np.ndarray, hp_period: int = ..., source_type: str = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
@overload
def decycler(candles: np.ndarray, hp_period: int = ..., source_type: str = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...

def decycler(candles: np.ndarray, hp_period: int = 125, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Ehlers Simple Decycler

    :param candles: np.ndarray
    :param hp_period: int - default: 125
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    hp = high_pass_2_pole_fast(source, hp_period)
    res = source - hp

    return res if sequential else res[-1]
