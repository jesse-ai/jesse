from typing import Union

import numpy as np

from jesse.helpers import slice_candles


def ultosc(candles: np.ndarray, timeperiod1: int = 7, timeperiod2: int = 14, timeperiod3: int = 28,
           sequential: bool = False) -> Union[float, np.ndarray]:
    """
    ULTOSC - Ultimate Oscillator

    :param candles: np.ndarray
    :param timeperiod1: int - default: 7
    :param timeperiod2: int - default: 14
    :param timeperiod3: int - default: 28
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]
    n = len(close)

    bp = np.empty(n, dtype=float)
    tr = np.empty(n, dtype=float)
    bp[0] = 0.0
    tr[0] = high[0] - low[0]
    bp[1:] = close[1:] - np.minimum(low[1:], close[:-1])
    tr[1:] = np.maximum(high[1:], close[:-1]) - np.minimum(low[1:], close[:-1])
    
    sum_bp_1 = _rolling_sum(bp, timeperiod1)
    sum_tr_1 = _rolling_sum(tr, timeperiod1)
    avg1 = np.where(sum_tr_1 != 0, sum_bp_1 / sum_tr_1, np.nan)

    sum_bp_2 = _rolling_sum(bp, timeperiod2)
    sum_tr_2 = _rolling_sum(tr, timeperiod2)
    avg2 = np.where(sum_tr_2 != 0, sum_bp_2 / sum_tr_2, np.nan)

    sum_bp_3 = _rolling_sum(bp, timeperiod3)
    sum_tr_3 = _rolling_sum(tr, timeperiod3)
    avg3 = np.where(sum_tr_3 != 0, sum_bp_3 / sum_tr_3, np.nan)

    ult = 100 * (4 * avg1 + 2 * avg2 + avg3) / 7

    return ult if sequential else ult[-1]

def _rolling_sum(data, window):
    n = len(data)
    if n < window:
        return np.full(n, np.nan)
    conv = np.convolve(data, np.ones(window, dtype=float), mode='valid')
    out = np.empty(n, dtype=float)
    out[:window-1] = np.nan
    out[window-1:] = conv
    return out
