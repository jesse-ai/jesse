from typing import Union

import numpy as np
import tulipy as ti

from jesse.helpers import get_candle_source, same_length
from jesse.helpers import slice_candles


def vidya(candles: np.ndarray, short_period: int = 2, long_period: int = 5, alpha: float = 0.2,
          source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    VIDYA - Variable Index Dynamic Average

    :param candles: np.ndarray
    :param short_period: int - default: 2
    :param long_period: int - default: 5
    :param alpha: float - default: 0.2
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    res = ti.vidya(np.ascontiguousarray(source), short_period=short_period, long_period=long_period, alpha=alpha)

    return same_length(candles, res) if sequential else res[-1]
