from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_candle_source

GATOR = namedtuple('GATOR', ['upper', 'lower', 'upper_change', 'lower_change'])


def gatorosc(candles: np.ndarray, source_type="close", sequential=False) -> GATOR:
    """
    Gator Oscillator by Bill M. Williams

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: GATOR(upper, lower, upper_change, lower_change)
    """

    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)

    jaw = shift(numpy_ewma(source, 13), 8)
    teeth = shift(numpy_ewma(source, 8), 5)
    lips = shift(numpy_ewma(source, 5), 3)

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


def numpy_ewma(data, window):
    alpha = 1 / window
    scale = 1 / (1 - alpha)
    n = data.shape[0]
    scale_arr = (1 - alpha) ** (-1 * np.arange(n))
    weights = (1 - alpha) ** np.arange(n)
    pw0 = (1 - alpha) ** (n - 1)
    mult = data * pw0 * scale_arr
    cumsums = mult.cumsum()
    out = cumsums * scale_arr[::-1] / weights.cumsum()

    return out
