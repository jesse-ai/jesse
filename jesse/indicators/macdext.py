from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_candle_source
from jesse.helpers import slice_candles

MACDEXT = namedtuple('MACDEXT', ['macd', 'signal', 'hist'])


def macdext(candles: np.ndarray, fast_period: int = 12, fast_matype: int = 0, slow_period: int = 26,
            slow_matype: int = 0, signal_period: int = 9, signal_matype: int = 0, source_type: str = "close",
            sequential: bool = False) -> MACDEXT:
    """
    MACDEXT - MACD with controllable MA type

    :param candles: np.ndarray
    :param fast_period: int - default: 12
    :param fastmatype: int - default: 0
    :param slow_period: int - default: 26
    :param slowmatype: int - default: 0
    :param signal_period: int - default: 9
    :param signalmatype: int - default: 0
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: MACDEXT(macd, signal, hist)
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    macd, macdsignal, macdhist = talib.MACDEXT(source, fastperiod=fast_period, fastmatype=fast_matype,
                                               slowperiod=slow_period, slowmatype=slow_matype,
                                               signalperiod=signal_period, signalmatype=signal_matype)

    if sequential:
        return MACDEXT(macd, macdsignal, macdhist)
    else:
        return MACDEXT(macd[-1], macdsignal[-1], macdhist[-1])
