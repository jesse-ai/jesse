from typing import Union

import numpy as np
import talib


def ultosc(candles: np.ndarray, timeperiod1=7, timeperiod2=14, timeperiod3=28, sequential=False) -> Union[
    float, np.ndarray]:
    """
    ULTOSC - Ultimate Oscillator

    :param candles: np.ndarray
    :param timeperiod1: int - default=7
    :param timeperiod2: int - default=14
    :param timeperiod3: int - default=28
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.ULTOSC(candles[:, 3], candles[:, 4], candles[:, 2], timeperiod1=timeperiod1, timeperiod2=timeperiod2,
                       timeperiod3=timeperiod3)

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
