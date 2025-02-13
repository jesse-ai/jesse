from collections import namedtuple

import numpy as np

from jesse.helpers import slice_candles

AC = namedtuple('AC', ['osc', 'change'])

def sma(arr: np.ndarray, period: int) -> np.ndarray:
    if len(arr) < period:
        return np.full_like(arr, np.nan, dtype=float)
    conv = np.convolve(arr, np.ones(period, dtype=float)/period, mode='valid')
    return np.concatenate((np.full(period-1, np.nan), conv))

def mom(arr: np.ndarray, period: int = 1) -> np.ndarray:
    return np.concatenate(([np.nan], np.diff(arr)))

def acosc(candles: np.ndarray, sequential: bool = False) -> AC:
    """
    Acceleration / Deceleration Oscillator (AC)

    :param candles: np.ndarray
    :param sequential: bool - default: False

    :return: AC(osc, change)
    """
    candles = slice_candles(candles, sequential)

    med = (candles[:, 3] + candles[:, 4]) / 2
    sma5_med = sma(med, 5)
    sma34_med = sma(med, 34)
    ao = sma5_med - sma34_med
    sma5_ao = sma(ao, 5)
    res = ao - sma5_ao
    mom_value = mom(res, 1)

    if sequential:
        return AC(res, mom_value)
    else:
        return AC(res[-1], mom_value[-1])
