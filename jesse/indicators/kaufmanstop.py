from typing import Union

import numpy as np

from jesse.indicators.ma import ma
from jesse.helpers import slice_candles


def kaufmanstop(candles: np.ndarray, period: int = 22, mult: float = 2, direction: str = "long", matype: int = 0,
                sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Perry Kaufman's Stops

    :param candles: np.ndarray
    :param period: int - default: 22
    :param mult: float - default: 2
    :param direction: str - default: long
    :param matype: int - default: 0
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    high = candles[:, 3]
    low = candles[:, 4]

    hl_diff = ma(high - low, period=period, matype=matype, sequential=True)

    res = low - hl_diff * mult if direction == "long" else high + hl_diff * mult 
    return res if sequential else res[-1]
