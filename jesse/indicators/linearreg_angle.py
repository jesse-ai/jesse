from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source
from jesse.helpers import slice_candles


def linearreg_angle(candles: np.ndarray, period: int = 14, source_type: str = "close", sequential: bool = False) -> \
        Union[float, np.ndarray]:
    """
    LINEARREG_ANGLE - Linear Regression Angle

    :param candles: np.ndarray
    :param period: int - default: 14
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    res = talib.LINEARREG_ANGLE(source, timeperiod=period)

    return res if sequential else res[-1]
