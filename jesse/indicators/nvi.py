from typing import Union

import numpy as np
import tulipy as ti

from jesse.helpers import get_candle_source, same_length
from jesse.helpers import slice_candles


def nvi(candles: np.ndarray, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    NVI - Negative Volume Index

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    res = ti.nvi(np.ascontiguousarray(source), np.ascontiguousarray(candles[:, 5]))

    return same_length(candles, res) if sequential else res[-1]
