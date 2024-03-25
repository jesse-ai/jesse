from typing import Union

import numpy as np
import tulipy as ti

from jesse.helpers import get_candle_source, same_length, slice_candles


def pvi(candles: np.ndarray, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    PVI - Positive Volume Index

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    res = ti.pvi(np.ascontiguousarray(source), np.ascontiguousarray(candles[:, 5]))

    return same_length(candles, res) if sequential else res[-1]
