from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source
from jesse.helpers import slice_candles


def stddev(candles: np.ndarray, period: int = 5, nbdev: float = 1, source_type: str = "close",
           sequential: bool = False) -> Union[float, np.ndarray]:
    """
    STDDEV - Standard Deviation

    :param candles: np.ndarray
    :param period: int - default: 5
    :param nbdev: float - default: 1
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    res = talib.STDDEV(source, timeperiod=period, nbdev=nbdev)

    return res if sequential else res[-1]
