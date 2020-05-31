import numpy as np
from .smma import smma
from jesse.helpers import get_candle_source
import talib

from collections import namedtuple

GATOR = namedtuple('GATOR', ['upper', 'lower', 'upper_change', 'lower_change'])


def gatorosc(candles: np.ndarray, source_type="close", sequential=False) -> GATOR:
    """
    Gator Oscillator by Bill M. Williams

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """

    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)

    jaw = shift(smma(source, period=13, sequential=True), 8)
    teeth = shift(smma(source, period=8, sequential=True), 5)
    lips = shift(smma(source, period=5, sequential=True), 3)

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