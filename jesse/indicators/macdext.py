import numpy as np
import talib
from collections import namedtuple

MACDEXT = namedtuple('MACDEXT', ['macd', 'signal', 'hist'])


def macdext(candles: np.ndarray, fastperiod=12, fastmatype=0, slowperiod=26, slowmatype=0, signalperiod=9, signalmatype=0, sequential=False) -> MACDEXT:
    """
    MACDEXT - MACD with controllable MA type
    https://www.investopedia.com/terms/m/macd.asp

    :param candles: np.ndarray
    :param fastperiod: int - default: 12
    :param fastmatype: int - default: 0
    :param slow_period: int - default: 26
    :param slowmatype: int - default: 0
    :param signal_period: int - default: 9
    :param signalmatype: int - default: 0
    :param sequential: bool - default: False

    :return: MACDEXT
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    macd, macdsignal, macdhist = talib.MACDEXT(candles[:, 2], fastperiod=fastperiod, fastmatype=fastmatype, slowperiod=slowperiod, slowmatype=slowmatype,
                                         signalperiod=signalperiod, signalmatype=signalmatype)

    if sequential:
        return MACDEXT(macd, macdsignal, macdhist)
    else:
        return MACDEXT(macd[-1], macdsignal[-1], macdhist[-1])
