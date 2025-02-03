from collections import namedtuple

import numpy as np

from jesse.helpers import slice_candles

CKSP = namedtuple('CKSP', ['long', 'short'])

def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, timeperiod: int = 10) -> np.ndarray:
    tr = np.empty_like(close)
    tr[0] = high[0] - low[0]
    tr[1:] = np.maximum.reduce([
        high[1:] - low[1:],
        np.abs(high[1:] - close[:-1]),
        np.abs(low[1:] - close[:-1])
    ])
    atr_vals = np.empty_like(close)
    if len(close) < timeperiod:
        return np.full_like(close, np.nan)
    atr_vals[:timeperiod-1] = np.nan
    atr_vals[timeperiod-1] = np.mean(tr[:timeperiod])
    for t in range(timeperiod, len(close)):
        atr_vals[t] = (atr_vals[t-1]*(timeperiod-1) + tr[t]) / timeperiod
    return atr_vals

def rolling_max(arr: np.ndarray, window: int) -> np.ndarray:
    n = len(arr)
    if n == 0:
        return arr
    result = np.empty(n)
    if window > 1:
        result[:window-1] = np.maximum.accumulate(arr[:window-1])
        if n >= window:
            shape = (n - window + 1, window)
            strides = (arr.strides[0], arr.strides[0])
            windows = np.lib.stride_tricks.as_strided(arr, shape=shape, strides=strides)
            result[window-1:] = np.max(windows, axis=1)
    else:
        result = arr.copy()
    return result

def rolling_min(arr: np.ndarray, window: int) -> np.ndarray:
    n = len(arr)
    if n == 0:
        return arr
    result = np.empty(n)
    if window > 1:
        result[:window-1] = np.minimum.accumulate(arr[:window-1])
        if n >= window:
            shape = (n - window + 1, window)
            strides = (arr.strides[0], arr.strides[0])
            windows = np.lib.stride_tricks.as_strided(arr, shape=shape, strides=strides)
            result[window-1:] = np.min(windows, axis=1)
    else:
        result = arr.copy()
    return result

def cksp(candles: np.ndarray, p: int = 10, x: float = 1.0,  q: int = 9, sequential: bool = False) -> CKSP:
    """
    Chande Kroll Stop (CKSP)

    :param candles: np.ndarray
    :param p: int - default: 10 (ATR period)
    :param x: float - default: 1.0 (ATR multiplier)
    :param q: int - default: 9 (rolling window period)
    :param sequential: bool - default: False

    :return: CKSP namedtuple containing long and short values
    """
    candles = slice_candles(candles, sequential)

    candles_close = candles[:, 2]
    candles_high = candles[:, 3]
    candles_low = candles[:, 4]

    atr_vals = atr(candles_high, candles_low, candles_close, timeperiod=p)

    LS0 = rolling_max(candles_high, window=q) - x * atr_vals
    LS = rolling_max(LS0, window=q)

    SS0 = rolling_min(candles_low, window=q) + x * atr_vals
    SS = rolling_min(SS0, window=q)

    if sequential:
        return CKSP(LS, SS)
    else:
        return CKSP(LS[-1], SS[-1])

