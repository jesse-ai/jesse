from typing import Union

import numpy as np
import talib

from jesse.helpers import get_config


def kaufmanstop(candles: np.ndarray, period: int = 22, mult: float = 2, direction: str = "long", sequential: bool = False) -> Union[
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
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    high = candles[:, 3]
    low = candles[:, 4]

    hl_diff = talib.SMA(high - low, period)

    if direction == "long":
        res = hl_diff * mult - low
    else:
        res = hl_diff * mult + high

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
