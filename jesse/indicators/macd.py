import numpy as np
import talib
from collections import namedtuple

MACD = namedtuple('MACD', ['macd', 'signal', 'hist'])


def macd(candles: np.ndarray, fastperiod=12, slowperiod=26, signalperiod=9, sequential=False) -> MACD:
    """
    MACD - Moving Average Convergence/Divergence
    https://www.investopedia.com/terms/m/macd.asp

    :param candles: np.ndarray
    :param fastperiod: int - default: 12
    :param slow_period: int - default: 26
    :param signal_period: int - default: 9
    :param sequential: bool - default: False

    :return: MACD
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    macd, macdsignal, macdhist = talib.MACD(candles[:, 2], fastperiod=fastperiod, slowperiod=slowperiod, signalperiod=signalperiod)

    if sequential:
        return MACD(macd, macdsignal, macdhist)
    else:
        return MACD(macd[-1], macdsignal[-1], macdhist[-1])
