from collections import namedtuple

import numpy as np
try:
    from numba import njit
except ImportError:
    njit = lambda a : a

from jesse.helpers import get_candle_source, slice_candles

VossFilter = namedtuple('VossFilter', ['voss', 'filt'])


def voss(candles: np.ndarray, period: int = 20, predict: int = 3, bandwith: float = 0.25, source_type: str = "close",
         sequential: bool = False) -> VossFilter:
    """
    Voss indicator by John F. Ehlers

    :param candles: np.ndarray
    :param period: int - default: 20
    :param predict: int - default: 3
    :param bandwith: float - default: 0.25
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """

    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    voss_val, filt = voss_fast(source, period, predict, bandwith)

    if sequential:
        return VossFilter(voss_val, filt)
    else:
        return VossFilter(voss_val[-1], filt[-1])


@njit
def voss_fast(source, period, predict, bandwith):
    voss = np.full_like(source, 0)
    filt = np.full_like(source, 0)

    pi = np.pi

    order = 3 * predict
    f1 = np.cos(2 * pi / period)
    g1 = np.cos(bandwith * 2 * pi / period)
    s1 = 1 / g1 - np.sqrt(1 / (g1 * g1) - 1)

    for i in range(source.shape[0]):
        if i > period and i > 5 and i > order:
            filt[i] = 0.5 * (1 - s1) * (source[i] - source[i - 2]) + f1 * (1 + s1) * filt[i - 1] - s1 * filt[i - 2]

    for i in range(source.shape[0]):
        if not (i <= period or i <= 5 or i <= order):
            sumc = 0
            for count in range(order):
                sumc = sumc + ((count + 1) / float(order)) * voss[i - (order - count)]
            voss[i] = ((3 + order) / 2) * filt[i] - sumc
    return voss, filt
