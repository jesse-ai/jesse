import numpy as np
import talib

from collections import namedtuple

MAMA = namedtuple('MAMA', ['mama', 'fama'])

def mama(candles: np.ndarray, fastlimit=0.5, slowlimit=0.05, sequential=False) -> MAMA:
    """
    MAMA - MESA Adaptive Moving Average

    :param candles: np.ndarray
    :param fastlimit: float - default: 0.5
    :param slowlimit: float - default: 0.05
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    mama, fama = talib.MAMA(candles[:, 2], fastlimit=fastlimit, slowlimit=slowlimit)

    if sequential:
        return MAMA(mama, fama)
    else:
        return MAMA(mama[-1], fama[-1])
