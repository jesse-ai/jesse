from typing import Union

import numpy as np
import talib

from jesse.helpers import get_config


def adosc(candles: np.ndarray, fast_period: int = 3, slow_period: int = 10, sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    ADOSC - Chaikin A/D Oscillator

    :param candles: np.ndarray
    :param fast_period: int - default: 3
    :param slow_period: int - default: 10
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    res = talib.ADOSC(candles[:, 3], candles[:, 4], candles[:, 2], candles[:, 5], fastperiod=fast_period,
                      slowperiod=slow_period)

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
