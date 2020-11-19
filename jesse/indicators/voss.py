import math
from collections import namedtuple

import numpy as np

from jesse.helpers import get_candle_source

VossFilter = namedtuple('VossFilter', ['voss', 'filt' ])


def voss(candles: np.ndarray, period=20, predict=3, bandwith=0.25, source_type="close", sequential=False) -> VossFilter:
    """
    Voss indicator by John F. Ehlers

    :param candles: np.ndarray
    :param period: int - default=20
    :param predict: int - default=3
    :param bandwith: float - default=0.25
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """

    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    voss = np.full_like(source, 0)
    filt = np.full_like(source, 0)

    pi = math.pi

    order = 3 * predict
    f1 = math.cos(2 * pi / period)
    g1 = math.cos(bandwith * 2 * pi / period)
    s1 = 1 / g1 - math.sqrt(1 / (g1 * g1) - 1)

    for i in range(source.shape[0]):
        if not (i <= period or i <= 5 or i <= order):
            filt[i] = 0.5 * (1 - s1) * (source[i] - source[i - 2]) + f1 * (1 + s1) * filt[i - 1] - s1 * filt[i - 2]

    for i in range(source.shape[0]):
        if not (i <= period or i <= 5 or i <= order):
            sumc = 0
            for count in range(order):
                sumc = sumc + ((count + 1) / float(order)) * voss[i - (order - count)]

            voss[i] = ((3 + order) / 2) * filt[i] - sumc

    if sequential:
        return VossFilter(voss, filt)
    else:
        return VossFilter(voss[-1], filt[-1])
