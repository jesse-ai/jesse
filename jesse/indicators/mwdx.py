from typing import Union

import numpy as np

try:
    from numba import njit
except ImportError:
    njit = lambda a: a

from jesse.helpers import get_candle_source, slice_candles


def mwdx(candles: np.ndarray, factor: float = 0.2, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    MWDX Average

    :param candles: np.ndarray
    :param factor: float - default: 0.2
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

    val2 = (2 / factor) - 1
    fac = 2 / (val2 + 1)

    res = mwdx_fast(source, fac)

    return res if sequential else res[-1]


@njit
def mwdx_fast(source, fac):
    newseries = np.copy(source)
    for i in range(1, source.shape[0]):
        newseries[i] = (fac * source[i]) + ((1 - fac) * newseries[i - 1])
    return newseries
