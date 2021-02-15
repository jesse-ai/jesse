from typing import Union

import numpy as np
import talib

from jesse.helpers import get_config


def ultosc(candles: np.ndarray, timeperiod1: int = 7, timeperiod2: int = 14, timeperiod3: int = 28,
           sequential: bool = False) -> Union[float, np.ndarray]:
    """
    ULTOSC - Ultimate Oscillator

    :param candles: np.ndarray
    :param timeperiod1: int - default=7
    :param timeperiod2: int - default=14
    :param timeperiod3: int - default=28
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    res = talib.ULTOSC(candles[:, 3], candles[:, 4], candles[:, 2], timeperiod1=timeperiod1, timeperiod2=timeperiod2,
                       timeperiod3=timeperiod3)

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
