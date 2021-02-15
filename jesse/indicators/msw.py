from collections import namedtuple

import numpy as np
import tulipy as ti

from jesse.helpers import get_candle_source
from jesse.helpers import get_config

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
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    source = get_candle_source(candles, source_type=source_type)
    msw_sine, msw_lead = ti.msw(np.ascontiguousarray(source), period=period)

    s = np.concatenate((np.full((candles.shape[0] - msw_sine.shape[0]), np.nan), msw_sine), axis=0)
    l = np.concatenate((np.full((candles.shape[0] - msw_lead.shape[0]), np.nan), msw_lead), axis=0)

    if sequential:
        return MSW(s, l)
    else:
        return MSW(s[-1], l[-1])
