from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_candle_source

SINEWAVE = namedtuple('SINEWAVE', ['sine', 'lead'])

def ht_sine(candles: np.ndarray, source_type="close", sequential=False) -> SINEWAVE:
    """
    HT_SINE - Hilbert Transform - SineWave

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: SINEWAVE(sine, lead)
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    sine, leadsine = talib.HT_SINE(source)

    if sequential:
        return SINEWAVE(sine, leadsine)
    else:
        return SINEWAVE(sine[-1], leadsine[-1])
