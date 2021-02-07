from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source


def rocr(candles: np.ndarray, period: int = 10, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    ROCR - Rate of change ratio: (price/prevPrice)

    :param candles: np.ndarray
    :param period: int - default=10
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    res = talib.ROCR(source, timeperiod=period)

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
