from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_candle_source

MACD = namedtuple('MACD', ['macd', 'signal', 'hist'])


def macd(candles: np.ndarray, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9,
         source_type: str = "close",
         sequential: bool = False) -> MACD:
    """
    MACD - Moving Average Convergence/Divergence

    :param candles: np.ndarray
    :param fast_period: int - default: 12
    :param slow_period: int - default: 26
    :param signal_period: int - default: 9
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: MACD(macd, signal, hist)
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    macd, macdsignal, macdhist = talib.MACD(source, fast_period=fast_period, slow_period=slow_period,
                                            signalperiod=signal_period)

    if sequential:
        return MACD(macd, macdsignal, macdhist)
    else:
        return MACD(macd[-1], macdsignal[-1], macdhist[-1])
