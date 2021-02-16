from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_candle_source
from jesse.helpers import get_config

SINEWAVE = namedtuple('SINEWAVE', ['sine', 'lead'])


def ht_sine(candles: np.ndarray, source_type: str = "close", sequential: bool = False) -> SINEWAVE:
    """
    HT_SINE - Hilbert Transform - SineWave

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: SINEWAVE(sine, lead)
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    source = get_candle_source(candles, source_type=source_type)
    sine, leadsine = talib.HT_SINE(source)

    if sequential:
        return SINEWAVE(sine, leadsine)
    else:
        return SINEWAVE(sine[-1], leadsine[-1])
