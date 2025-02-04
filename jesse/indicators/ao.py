from collections import namedtuple

import numpy as np

from jesse.helpers import slice_candles
from .sma import sma

AO = namedtuple('AO', ['osc', 'change'])

def momentum(arr):
    ret = np.full(arr.shape, np.nan)
    if len(arr) > 1:
        ret[1:] = arr[1:] - arr[:-1]
    return ret

def ao(candles: np.ndarray, sequential: bool = False) -> AO:
    """
    Awesome Oscillator

    :param candles: np.ndarray
    :param sequential: bool - default: False

    :return: AO(osc, change)
    """
    candles = slice_candles(candles, sequential)

    # Calculate hl2 as (high+low)/2
    hl2 = (candles[:, 3] + candles[:, 4]) / 2
    # Calculate simple moving averages on hl2 for periods 5 and 34
    sma5 = sma(hl2, 5, sequential=True)
    sma34 = sma(hl2, 34, sequential=True)
    ao = sma5 - sma34

    # Calculate momentum as the difference between consecutive values
    mom = momentum(ao)

    if sequential:
        return AO(ao, mom)
    else:
        return AO(ao[-1], mom[-1])
