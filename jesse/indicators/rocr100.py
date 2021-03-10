from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source
from jesse.helpers import slice_candles


def rocr100(candles: np.ndarray, period: int = 10, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    ROCR100 - Rate of change ratio 100 scale: (price/prevPrice)*100

    :param candles: np.ndarray
    :param period: int - default=10
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    res = talib.ROCR100(source, timeperiod=period)

    return res if sequential else res[-1]
