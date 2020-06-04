from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_candle_source

MACDEXT = namedtuple('MACDEXT', ['macd', 'signal', 'hist'])


def macdext(candles: np.ndarray, fastperiod=12, fastmatype=0, slowperiod=26, slowmatype=0, signalperiod=9,
            signalmatype=0, source_type="close", sequential=False) -> MACDEXT:
    """
    MACDEXT - MACD with controllable MA type

    :param candles: np.ndarray
    :param fastperiod: int - default: 12
    :param fastmatype: int - default: 0
    :param slow_period: int - default: 26
    :param slowmatype: int - default: 0
    :param signal_period: int - default: 9
    :param signalmatype: int - default: 0
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: MACDEXT(macd, signal, hist)
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    macd, macdsignal, macdhist = talib.MACDEXT(source, fastperiod=fastperiod, fastmatype=fastmatype,
                                               slowperiod=slowperiod, slowmatype=slowmatype,
                                               signalperiod=signalperiod, signalmatype=signalmatype)

    if sequential:
        return MACDEXT(macd, macdsignal, macdhist)
    else:
        return MACDEXT(macd[-1], macdsignal[-1], macdhist[-1])
