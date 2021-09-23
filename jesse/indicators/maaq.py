from typing import Union
import talib
import numpy as np

try:
    from numba import njit
except ImportError:
    njit = lambda a : a

from jesse.helpers import get_candle_source, slice_candles, np_shift, same_length


def maaq(candles: np.ndarray, period: int = 11, fast_period: int = 2, slow_period: int = 30, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Moving Average Adaptive Q

    :param candles: np.ndarray
    :param period: int - default: 11
    :param fast_period: int - default: 2
    :param slow_period: int - default: 30
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

    source = source[~np.isnan(source)]

    diff = np.abs(source - np_shift(source, 1, np.nan))
    signal = np.abs(source - np_shift(source, period, np.nan))
    noise = talib.SUM(diff, period)

    with np.errstate(divide='ignore'):
        ratio = np.where(noise == 0, 0, signal / noise)

    fastSc = 2 / (fast_period + 1)
    slowSc = 2 / (slow_period + 1)
    temp = np.power((ratio * fastSc) + slowSc, 2)

    res = maaq_fast(source, temp, period)
    res = same_length(candles, res)

    return res if sequential else res[-1]


@njit
def maaq_fast(source, temp, period):
    newseries = np.copy(source)
    for i in range(period, source.shape[0]):
        newseries[i] = newseries[i - 1] + (temp[i] * (source[i] - newseries[i - 1]))
    return newseries
