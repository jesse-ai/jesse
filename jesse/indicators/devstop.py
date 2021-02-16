from typing import Union

import numpy as np
import talib

from jesse.helpers import get_config

def devstop(candles: np.ndarray, period:int=20, mult: float = 0, direction: str = "long", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Kase Dev Stops

    :param candles: np.ndarray
    :param period: int - default=20
    :param mult: float - default=0
    :param direction: str - default=long
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    high = candles[:, 3]
    low = candles[:, 4]

    AVTR = talib.SMA(talib.MAX(high, 2) - talib.MIN(low, 2), period)
    SD = talib.STDDEV(talib.MAX(high, 2) - talib.MIN(low, 2), period)

    if direction == "long":
        res = talib.MAX(high - AVTR - mult * SD, period)
    else:
        res = talib.MIN(low + AVTR + mult * SD, period)

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
