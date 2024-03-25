from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source, slice_candles


def cfo(candles: np.ndarray, period: int = 14, scalar: float = 100, source_type: str = "close",
        sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    CFO - Chande Forcast Oscillator

    :param candles: np.ndarray
    :param period: int - default: 14
    :param scalar: float - default: 100
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    res = scalar * (source - talib.LINEARREG(source, timeperiod=period))
    res /= source

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
