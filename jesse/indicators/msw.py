from collections import namedtuple

import numpy as np
import tulipy as ti

from jesse.helpers import get_candle_source

MSW = namedtuple('MSW', ['sine', 'lead'])

def msw(candles: np.ndarray, period=5, source_type="close", sequential=False) -> MSW:
    """
    MSW - Mesa Sine Wave

    :param candles: np.ndarray
    :param period: int - default: 5
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: MSW(sine, lead)
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    msw_sine, msw_lead = ti.msw(np.ascontiguousarray(source), period=period)

    s = np.concatenate((np.full((candles.shape[0] - msw_sine.shape[0]), np.nan), msw_sine), axis=0)
    l = np.concatenate((np.full((candles.shape[0] - msw_lead.shape[0]), np.nan), msw_lead), axis=0)

    if sequential:
        return MSW(s, l)
    else:
        return MSW(s[-1], l[-1])