from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source


def trix(candles: np.ndarray, period=18, source_type="close", sequential=False) -> Union[float, np.ndarray]:
    """
    TRIX - 1-day Rate-Of-Change (ROC) of a Triple Smooth EMA

    :param candles: np.ndarray
    :param period: int - default: 18
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    r = talib.TRIX(source, timeperiod=period) * 100

    return r if sequential else r[-1]
