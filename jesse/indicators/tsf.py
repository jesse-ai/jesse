from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source


def tsf(candles: np.ndarray, period: int = 14, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    TSF - Time Series Forecast

    :param candles: np.ndarray
    :param period: int - default: 14
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    res = talib.TSF(source, timeperiod=period)

    return res if sequential else res[-1]
