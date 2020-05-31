import numpy as np
from .smma import smma
from jesse.helpers import get_candle_source
from collections import namedtuple

AG = namedtuple('AG', ['jaw', 'teeth', 'lips'])


def alligator(candles: np.ndarray, source_type="close", sequential=False) -> AG:
    """
    Alligator

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

    if sequential:
        return AG(jaw, teeth, lips)
    else:
        return AG(jaw[-1], teeth[-1], lips[-1])


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