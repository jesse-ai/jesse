from typing import Union

import numpy as np
import tulipy as ti

from jesse.helpers import get_candle_source, same_length
from jesse.helpers import slice_candles


def wilders(candles: np.ndarray, period: int = 5, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    WILDERS - Wilders Smoothing

    :param candles: np.ndarray
    :param period: int - default: 5
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    res = ti.wilders(np.ascontiguousarray(source), period=period)

    return same_length(candles, res) if sequential else res[-1]
