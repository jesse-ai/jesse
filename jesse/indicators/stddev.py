from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source


def stddev(candles: np.ndarray, period=5, nbdev=1, source_type="close", sequential=False) -> Union[float, np.ndarray]:
    """
    STDDEV - Standard Deviation

    :param candles: np.ndarray
    :param period: int - default: 5
    :param nbdev: int - default: 1
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    res = talib.STDDEV(source, timeperiod=period, nbdev=nbdev)

    return res if sequential else res[-1]
