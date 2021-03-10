from typing import Union

import numpy as np
import talib

from jesse.helpers import slice_candles


def kaufmanstop(candles: np.ndarray, period: int = 22, mult: float = 2, direction: str = "long",
                sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Perry Kaufman's Stops

    :param candles: np.ndarray
    :param period: int - default=22
    :param mult: float - default=2
    :param direction: str - default=long
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    high = candles[:, 3]
    low = candles[:, 4]

    hl_diff = talib.SMA(high - low, period)

    if direction == "long":
        res = hl_diff * mult - low
    else:
        res = hl_diff * mult + high

    return res if sequential else res[-1]
