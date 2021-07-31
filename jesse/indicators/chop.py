from typing import Union

import numpy as np
import talib

from jesse.helpers import slice_candles


def chop(candles: np.ndarray, period: int = 14, scalar: float = 100, drift: int = 1, sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Choppiness Index (CHOP)

    :param candles: np.ndarray
    :param period: int - default: 30
    :param scalar: float - default: 100
    :param drift: int - default: 1
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)


    candles_close = candles[:, 2]
    candles_high = candles[:, 3]
    candles_low = candles[:, 4]

    atr_sum = talib.SUM(talib.ATR(candles_high, candles_low, candles_close, timeperiod=drift), period)

    hh = talib.MAX(candles_high, period)
    ll = talib.MIN(candles_low, period)

    res = (scalar * (np.log10(atr_sum) - np.log10(hh - ll))) / np.log10(period)

    return res if sequential else res[-1]
