from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, same_length, slice_candles


def hwma(candles: np.ndarray, na: float = 0.2, nb: float = 0.1, nc: float = 0.1, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Holt-Winter Moving Average

    :param candles: np.ndarray
    :param na: float - default: 0.2
    :param nb: float - default: 0.1
    :param nc: float - default: 0.1
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if not ((0 < na < 1) or (0 < nb < 1) or (0 < nc < 1)):
        raise ValueError("Bad parameters. They have to be: 0 < na nb nc < 1")

    # Accept normal array too.
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    source_without_nan = source[~np.isnan(source)]
    res = hwma_fast(source_without_nan, na, nb, nc)
    res = same_length(candles, res)

    return res if sequential else res[-1]


@njit(cache=True)
def hwma_fast(source, na, nb, nc):
    last_a = last_v = 0
    last_f = source[0]
    newseries = np.copy(source)
    for i in range(source.size):
        F = (1.0 - na) * (last_f + last_v + 0.5 * last_a) + na * source[i]
        V = (1.0 - nb) * (last_v + last_a) + nb * (F - last_f)
        A = (1.0 - nc) * last_a + nc * (V - last_v)
        newseries[i] = F + V + 0.5 * A
        last_a, last_f, last_v = A, F, V  # update values
    return newseries
