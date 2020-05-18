import numpy as np
from .smma import smma

import talib

from collections import namedtuple

GATOR = namedtuple('GATOR', ['upper', 'lower', 'upper_change', 'lower_change'])


def gatorosc(candles: np.ndarray, sequential=False) -> GATOR:
    """
    Gator Oscillator by Bill M. Williams

    :param candles: np.ndarray
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    jaw = shift(smma(candles, period=13, sequential=True), 8)
    teeth = shift(smma(candles, period=8, sequential=True), 5)
    lips = shift(smma(candles, period=5, sequential=True), 3)

    upper = np.abs(jaw - teeth)
    lower = -np.abs(teeth - lips)

    upper_change = talib.MOM(upper, timeperiod=1)
    lower_change = -talib.MOM(lower, timeperiod=1)

    if sequential:
        return GATOR(upper, lower, upper_change, lower_change)
    else:
        return GATOR(upper[-1], lower[-1], upper_change[-1], lower_change[-1])


# preallocate empty array and assign slice by chrisaycock
def shift(arr, num, fill_value=np.nan):
    result = np.empty_like(arr)
    if num > 0:
        result[:num] = fill_value
        result[num:] = arr[:-num]
    elif num < 0:
        result[num:] = fill_value
        result[:num] = arr[-num:]
    else:
        result[:] = arr
    return result