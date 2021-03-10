from collections import namedtuple

import numpy as np
import tulipy as ti

from jesse.helpers import get_candle_source, same_length, slice_candles

MSW = namedtuple('MSW', ['sine', 'lead'])


def msw(candles: np.ndarray, period: int = 5, source_type: str = "close", sequential: bool = False) -> MSW:
    """
    MSW - Mesa Sine Wave

    :param candles: np.ndarray
    :param period: int - default: 5
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: MSW(sine, lead)
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    msw_sine, msw_lead = ti.msw(np.ascontiguousarray(source), period=period)

    s = same_length(candles, msw_sine)
    l = same_length(candles, msw_lead)

    if sequential:
        return MSW(s, l)
    else:
        return MSW(s[-1], l[-1])
