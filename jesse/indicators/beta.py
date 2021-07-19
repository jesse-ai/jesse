from typing import Union

import numpy as np
import talib

from jesse.helpers import slice_candles


def beta(candles: np.ndarray, period: int = 5, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    BETA - Beta

    :param candles: np.ndarray
    :param period: int - default: 5
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    res = talib.BETA(candles[:, 3], candles[:, 4], timeperiod=period)

    return res if sequential else res[-1]
