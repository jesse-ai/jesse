from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source, slice_candles


def ui(candles: np.ndarray, period: int = 14, scalar: float = 100, source_type: str = "close",  sequential: bool = False) -> Union[float, np.ndarray]:
    """
    Ulcer Index (UI)

    :param candles: np.ndarray
    :param period: int - default: 14
    :param scalar: float - default: 100
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)

    highest_close = talib.MAX(source, period)
    downside = scalar * (source - highest_close)
    downside /= highest_close
    d2 = downside * downside

    res = np.sqrt(talib.SUM(d2, period) / period)

    return res if sequential else res[-1]
