from typing import Union

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from math import pi
from math import sin

from jesse.helpers import get_candle_source


def sinwma(candles: np.ndarray, period=14, source_type="close", sequential=False) -> Union[float, np.ndarray]:
    """
    Sine Weighted Moving Average (SINWMA)

    :param candles: np.ndarray
    :param period: int - default: 14
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    sines = np.array([sin((i + 1) * pi / (period + 1)) for i in range(0, period)])
    w = sines / sines.sum()
    swv = sliding_window_view(source, window_shape=period)
    res = np.average(swv, weights=w, axis=-1)

    return np.concatenate((np.full((candles.shape[0] - res.shape[0]), np.nan), res), axis=0) if sequential else res[-1]
