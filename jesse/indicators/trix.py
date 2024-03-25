from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source, slice_candles


def trix(candles: np.ndarray, period: int = 18, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    TRIX - 1-day Rate-Of-Change (ROC) of a Triple Smooth EMA

    :param candles: np.ndarray
    :param period: int - default: 18
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    r = talib.TRIX(source, timeperiod=period) * 100

    return r if sequential else r[-1]
