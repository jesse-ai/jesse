from typing import Union

import numpy as np
from scipy.ndimage import maximum_filter1d, minimum_filter1d
from numba import njit

from jesse.helpers import slice_candles


@njit(cache=True)
def custom_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """Compute the Average True Range (ATR) using Wilder's smoothing method."""
    # Compute previous close
    prev_close = np.empty_like(close)
    prev_close[0] = close[0]
    prev_close[1:] = close[:-1]

    # Compute True Range (TR)
    range1 = high - low
    range2 = np.abs(high - prev_close)
    range3 = np.abs(low - prev_close)
    tr = np.maximum(range1, range2)
    tr = np.maximum(tr, range3)

    atr = np.full(len(close), np.nan, dtype=close.dtype)
    if len(close) >= period:
        initial_atr = np.mean(tr[:period])
        atr[period - 1] = initial_atr
        alpha = 1.0 / period
        for i in range(period, len(close)):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def chande(candles: np.ndarray, period: int = 22, mult: float = 3.0, direction: str = "long",
           sequential: bool = False) -> Union[float, np.ndarray]:
    """
    Chandelier Exits

    :param candles: np.ndarray
    :param period: int - default: 22
    :param mult: float - default: 3.0
    :param direction: str - default: "long"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    candles_close = candles[:, 2]
    candles_high = candles[:, 3]
    candles_low = candles[:, 4]

    atr = custom_atr(candles_high, candles_low, candles_close, period)

    if direction == 'long':
        maxp = filter1d_same(candles_high, period, 'max')
        result = maxp - atr * mult
    elif direction == 'short':
        maxp = filter1d_same(candles_low, period, 'min')
        result = maxp + atr * mult
    else:
        print('The last parameter must be \'short\' or \'long\'')

    return result if sequential else result[-1]


def filter1d_same(a: np.ndarray, W: int, max_or_min: str, fillna=np.nan):
    out_dtype = np.full(0, fillna).dtype
    hW = (W - 1) // 2  # Half window size
    if max_or_min == 'max':
        out = maximum_filter1d(a, size=W, origin=hW)
    else:
        out = minimum_filter1d(a, size=W, origin=hW)
    if out.dtype is out_dtype:
        out[:W - 1] = fillna
    else:
        out = np.concatenate((np.full(W - 1, fillna), out[W - 1:]))
    return out
