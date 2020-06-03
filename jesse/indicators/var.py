from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source

def var(candles: np.ndarray, period=14, nbdev=1, source_type="close", sequential=False) -> Union[float, np.ndarray]:
    """
    VAR - Variance

    :param candles: np.ndarray
    :param period: int - default=14
    :param nbdev: int - default=1
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    res = talib.VAR(candles[:, 2], timeperiod=period, nbdev=nbdev)

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
