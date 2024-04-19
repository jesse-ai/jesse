from collections import namedtuple

import numpy as np

from jesse.helpers import get_candle_source, slice_candles
from jesse.indicators.ma import ma

ERI = namedtuple('ERI', ['bull', 'bear'])


def eri(candles: np.ndarray, period: int = 13, matype: int = 1, source_type: str = "close",
        sequential: bool = False) -> ERI:
    """
    Elder Ray Index (ERI)

    :param candles: np.ndarray
    :param period: int - default: 13
    :param matype: int - default: 1
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    ema = ma(source, period=period, matype=matype, sequential=True)
    bull = candles[:, 3] - ema
    bear = candles[:, 4] - ema

    if sequential:
        return ERI(bull, bear)
    else:
        return ERI(bull[-1], bear[-1])
