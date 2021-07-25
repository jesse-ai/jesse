from typing import Union
from functools import reduce
from operator import mul

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from jesse.helpers import get_candle_source, slice_candles, same_length


def pwma(candles: np.ndarray, period: int = 5, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Pascals Weighted Moving Average (PWMA)

    :param candles: np.ndarray
    :param period: int - default: 5
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """

    # Accept normal array too.
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    triangle = pascals_triangle(n=period - 1)
    swv = sliding_window_view(source, window_shape=period)
    res = np.average(swv, weights=triangle, axis=-1)

    return same_length(candles, res) if sequential else res[-1]


def pascals_triangle(n: int = None) -> np.ndarray:
    """Pascal's Triangle
    Returns a numpy array of the nth row of Pascal's Triangle.
    n=4  => triangle: [1, 4, 6, 4, 1]
         => weighted: [0.0625, 0.25, 0.375, 0.25, 0.0625]
    """
    n = int(np.fabs(n)) if n is not None else 0

    # Calculation
    triangle = np.array([combination(n=n, r=i) for i in range(n + 1)])
    triangle_sum = np.sum(triangle)
    return triangle / triangle_sum


def combination(n, r) -> int:
    """https://stackoverflow.com/questions/4941753/is-there-a-math-ncr-function-in-python"""
    n = int(np.fabs(n))
    r = int(np.fabs(r))

    r = min(n, n - r)
    if r == 0:
      return 1

    numerator = reduce(mul, range(n, n - r, -1), 1)
    denominator = reduce(mul, range(1, r + 1), 1)
    return numerator // denominator
