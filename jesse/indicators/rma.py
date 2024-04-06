from typing import Union

import numpy as np
from numba import guvectorize, njit

from jesse.helpers import get_candle_source, slice_candles


def rma(candles: np.ndarray, length: int = 14, source_type="close", sequential=False) -> \
        Union[float, np.ndarray]:
    """
    Moving average used in RSI. It is the exponentially weighted moving average with alpha = 1 / length.
    RETURNS Exponential moving average of x with alpha = 1 / y.
    https://www.tradingview.com/pine-script-reference/#fun_rma

    :param candles: np.ndarray
    :param length: int - default: 14
    :param source_type: str - default: close
    :param sequential: bool - default: False
    :return: Union[float, np.ndarray]
    """

    if length < 1:
        raise ValueError('Bad parameters.')

    # Accept normal array too.
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    res = rma_fast(source, length)
    return res if sequential else res[-1]


@njit(cache=True)
def rma_fast(source, _length):
    alpha = 1 / _length
    newseries = np.copy(source)
    out = np.full_like(source, np.nan)
    for i in range(source.size):
        if np.isnan(newseries[i - 1]):
            # Sma in Numba
            asum = 0.0
            count = 0
            for i in range(_length):
                asum += source[i]
                count += 1
                out[i] = asum / count
            for i in range(_length, len(source)):
                asum += source[i] - source[i - _length]
                out[i] = asum / count
            newseries[i] = out[-1]
        else:
            prev = newseries[i - 1]
            if np.isnan(prev):
                prev = 0
            newseries[i] = alpha * source[i] + (1 - alpha) * prev
    return newseries
