from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source
from jesse.helpers import slice_candles


def cfo(candles: np.ndarray, period: int = 14, scalar: float = 100, source_type: str = "close",
        sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    CFO - Chande Forcast Oscillator

    :param candles: np.ndarray
    :param period: int - default=14
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    cfo = scalar * (source - talib.LINEARREG(source, timeperiod=period))
    cfo /= source

    if sequential:
        return cfo
    else:
        return None if np.isnan(cfo[-1]) else cfo[-1]
