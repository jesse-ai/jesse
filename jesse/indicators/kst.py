from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_candle_source

KST = namedtuple('KST', ['line', 'signal'])


def kst(candles: np.ndarray, sma_period1=10, sma_period2=10, sma_period3=10, sma_period4=15, roc_period1=10, roc_period2=15, roc_period3=20, roc_period4=30, signal_period=9, source_type="close", sequential=False) -> KST:
    """
    Know Sure Thing (KST)

    :param candles: np.ndarray
    :param sma_period1: int - default=10
    :param sma_period2: int - default=10
    :param sma_period3: int - default=10
    :param sma_period4: int - default=15
    :param roc_period1: int - default=10
    :param roc_period2: int - default=15
    :param roc_period3: int - default=20
    :param roc_period4: int - default=30
    :param signal_period: int - default=9
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: KST(line, signal)
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]


    source = get_candle_source(candles, source_type=source_type)


    aroc1 = talib.SMA(talib.ROC(source, timeperiod=roc_period1), sma_period1)
    aroc2 = talib.SMA(talib.ROC(source, timeperiod=roc_period2), sma_period2)
    aroc3 = talib.SMA(talib.ROC(source, timeperiod=roc_period3), sma_period3)
    aroc4 = talib.SMA(talib.ROC(source, timeperiod=roc_period4), sma_period4)
    line = aroc1[len(aroc1) - len(aroc4):] + 2 * aroc2[len(aroc2) - len(aroc4):] + \
           3 * aroc3[len(aroc3) - len(aroc4):] + 4 * aroc4
    signal = talib.SMA(line, signal_period)

    if sequential:
        return KST(line, signal)
    else:
        return KST(line[-1], signal[-1])
