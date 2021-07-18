from typing import Union

import numpy as np
import talib

import jesse.helpers as jh
from jesse.helpers import slice_candles


def dti(candles: np.ndarray, r: int = 14, s: int = 10, u: int = 5, sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    DTI by William Blau

    :param candles: np.ndarray
    :param r: int - default: 14
    :param s: int - default: 10
    :param u: int - default: 5
    :param sequential: bool - default: False

    :return: float
    """
    candles = slice_candles(candles, sequential)

    high = candles[:, 3]
    low = candles[:, 4]

    high_1 = jh.np_shift(high, 1, np.nan)
    low_1 = jh.np_shift(low, 1, np.nan)

    xHMU = np.where(high - high_1 > 0, high - high_1, 0)
    xLMD = np.where(low - low_1 < 0, -(low - low_1), 0)

    xPrice = xHMU - xLMD
    xPriceAbs = np.absolute(xPrice)

    xuXA = talib.EMA(talib.EMA(talib.EMA(xPrice, r), s), u)
    xuXAAbs = talib.EMA(talib.EMA(talib.EMA(xPriceAbs, r), s), u)

    Val1 = 100 * xuXA
    Val2 = xuXAAbs
    dti_val = np.where(Val2 != 0, Val1 / Val2, 0)

    if sequential:
        return dti_val
    else:
        return None if np.isnan(dti_val[-1]) else dti_val[-1]
