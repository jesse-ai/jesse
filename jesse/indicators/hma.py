from typing import Union

import numpy as np
import tulipy as ti

from jesse.helpers import get_candle_source


def hma(candles: np.ndarray, period=5, source_type="close", sequential=False) -> Union[float, np.ndarray]:
    """
    Hull Moving Average

    :param candles: np.ndarray
    :param period: int - default: 5
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    res = ti.hma(np.ascontiguousarray(source), period=period)

    return np.concatenate((np.full((candles.shape[0] - res.shape[0]), np.nan), res), axis=0) if sequential else res[-1]
