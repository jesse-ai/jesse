from math import fabs
from typing import Union

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from jesse.helpers import get_candle_source, slice_candles, same_length


def fwma(candles: np.ndarray, period: int = 5, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Fibonacci's Weighted Moving Average (FWMA)

    :param candles: np.ndarray
    :param period: int - default: 5
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """

    # Accept normal array too.
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    fibs = fibonacci(n=period)
    swv = sliding_window_view(source, window_shape=period)
    res = np.average(swv, weights=fibs, axis=-1)

    return same_length(candles, res) if sequential else res[-1]


def fibonacci(n: int = 2) -> np.ndarray:
    """Fibonacci Sequence as a numpy array"""
    n = int(fabs(n)) if n >= 0 else 2

    n -= 1
    a, b = 1, 1

    result = np.array([a])

    for i in range(0, n):
        a, b = b, a + b
        result = np.append(result, a)

    fib_sum = np.sum(result)
    if fib_sum > 0:
        return result / fib_sum
    else:
        return result
