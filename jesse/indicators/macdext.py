from collections import namedtuple

import numpy as np

from jesse.helpers import get_candle_source
from jesse.helpers import slice_candles
from jesse.indicators.ma import ma

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

    macd = ma(source, period=fast_period, matype=fast_matype, sequential=True) - ma(source, period=slow_period, matype=slow_matype, sequential=True)
    macdsignal = ma(macd, period=signal_period, matype=signal_matype, sequential=True)
    macdhist = macd - macdsignal

    if sequential:
        return MACDEXT(macd, macdsignal, macdhist)
    else:
        return MACDEXT(macd[-1], macdsignal[-1], macdhist[-1])
