from typing import Union
from math import floor
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from jesse.helpers import get_candle_source, slice_candles, same_length


def swma(candles: np.ndarray, period: int = 5, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Symmetric Weighted Moving Average (SWMA)

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

    triangle = symmetric_triangle(period)
    swv = sliding_window_view(source, window_shape=period)
    res = np.average(swv, weights=triangle, axis=-1)

    return same_length(candles, res) if sequential else res[-1]



def symmetric_triangle(n: int = None) -> np.ndarray:
    """Symmetric Triangle with n >= 2
    Returns a numpy array of the nth row of Symmetric Triangle.
    n=4  => triangle: [1, 2, 2, 1]
         => weighted: [0.16666667 0.33333333 0.33333333 0.16666667]
    """
    n = int(np.fabs(n)) if n is not None else 2

    triangle = None
    if n == 2:
        triangle = [1, 1]

    if n > 2:
        if n % 2 == 0:
            front = [i + 1 for i in range(floor(n / 2))]
            triangle = front + front[::-1]
        else:
            front = [i + 1 for i in range(floor(0.5 * (n + 1)))]
            triangle = front.copy()
            front.pop()
            triangle += front[::-1]


    triangle_sum = np.sum(triangle)
    return triangle / triangle_sum


