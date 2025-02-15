from typing import Union

import numpy as np
from jesse.helpers import get_candle_source, slice_candles


def rocp(candles: np.ndarray, period: int = 10, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    ROCP - Rate of change Percentage: (price-prevPrice)/prevPrice

    :param candles: np.ndarray
    :param period: int - default: 10
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    res = np.full(source.shape, np.nan, dtype=float)
    if len(source) > period:
        res[period:] = (source[period:] - source[:-period]) / source[:-period]

    return res if sequential else res[-1]
