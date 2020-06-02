import math
from typing import Union

import numpy as np

from jesse.helpers import get_candle_source


def supersmoother(candles: np.ndarray, cutoff=14, source_type="close", sequential=False) -> Union[float, np.ndarray]:
    """
    Super Smoother Filter 2pole Butterworth
    This indicator was described by John F. Ehlers

    :param candles: np.ndarray
    :param cutoff: int - default=14
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """

    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    source = source.flatten()
    N = len(source)
    source = source[~np.isnan(source)]
    to_fill = N - len(source)

    PI = math.pi
    f = (math.sqrt(2) * PI) / cutoff
    a = math.exp(-f)
    c2 = 2 * a * math.cos(f)
    c3 = -a * a
    c1 = 1 - c2 - c3

    src = np.insert(source, 0, 0)
    coeff = np.array([0.5 * c1, 0.5 * c1, c2, c3])
    fil = np.zeros(2 + len(source))
    for i in range(len(source)):
        val = np.array([src[i,], src[i + 1,], fil[i + 1], fil[i]])
        fil[2 + i] = np.dot(coeff, val)
    if to_fill != 0:
        out = np.insert(fil[2:], 0, np.repeat(np.nan, to_fill))
    else:
        out = fil[2:]

    res = out

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
