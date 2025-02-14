from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import slice_candles

@njit(cache=True)
def calculate_cci_loop(tp, period):
    n = tp.shape[0]
    result = np.empty(n)
    # initialize result with NaNs
    for i in range(n):
        result[i] = np.nan
    if n < period:
        return result
    for i in range(period - 1, n):
        sum_tp = 0.0
        for j in range(i - period + 1, i + 1):
            sum_tp += tp[j]
        sma = sum_tp / period
        sum_diff = 0.0
        for j in range(i - period + 1, i + 1):
            # Calculate absolute deviation
            if tp[j] >= sma:
                sum_diff += tp[j] - sma
            else:
                sum_diff += sma - tp[j]
        md = sum_diff / period
        if md == 0.0:
            result[i] = 0.0
        else:
            result[i] = (tp[i] - sma) / (0.015 * md)
    return result


def cci(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    CCI - Commodity Channel Index

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]
    tp = (high + low + close) / 3.0

    result = calculate_cci_loop(tp, period)
    return result if sequential else result[-1]
