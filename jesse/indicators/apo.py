from typing import Union

import numpy as np
from jesse.indicators.ma import ma

from jesse.helpers import get_candle_source, slice_candles


def apo(candles: np.ndarray, fast_period: int = 12, slow_period: int = 26, matype: int = 0, source_type: str = "close",
        sequential: bool = False) -> Union[float, np.ndarray]:
    """
    APO - Absolute Price Oscillator

    :param candles: np.ndarray
    :param fast_period: int - default: 12
    :param slow_period: int - default: 26
    :param matype: int - default: 0
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    res = ma(source, period=fast_period, matype=matype, sequential=True) - ma(source, period=slow_period, matype=matype, sequential=True)

    return res if sequential else res[-1]
