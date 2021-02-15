from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_candle_source
from jesse.helpers import get_config

MAMA = namedtuple('MAMA', ['mama', 'fama'])


def mama(candles: np.ndarray, fastlimit: float = 0.5, slowlimit: float = 0.05, source_type: str = "close",
         sequential: bool = False) -> MAMA:
    """
    MAMA - MESA Adaptive Moving Average

    :param candles: np.ndarray
    :param fastlimit: float - default: 0.5
    :param slowlimit: float - default: 0.05
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: MAMA(mama, fama)
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    source = get_candle_source(candles, source_type=source_type)
    mama, fama = talib.MAMA(source, fastlimit=fastlimit, slowlimit=slowlimit)

    if sequential:
        return MAMA(mama, fama)
    else:
        return MAMA(mama[-1], fama[-1])
