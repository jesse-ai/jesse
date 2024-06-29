from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_candle_source, slice_candles

SINEWAVE = namedtuple('SINEWAVE', ['sine', 'lead'])


def ht_sine(candles: np.ndarray, source_type: str = "close", sequential: bool = False) -> SINEWAVE:
    """
    HT_SINE - Hilbert Transform - SineWave

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: SINEWAVE(sine, lead)
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    sine, leadsine = talib.HT_SINE(source)

    if sequential:
        return SINEWAVE(sine, leadsine)
    else:
        return SINEWAVE(sine[-1], leadsine[-1])
