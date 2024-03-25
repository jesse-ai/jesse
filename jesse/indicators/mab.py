from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_candle_source, slice_candles
from jesse.indicators.ma import ma

MAB = namedtuple('MAB', ['upperband', 'middleband', 'lowerband'])


def mab(candles: np.ndarray, fast_period: int = 10, slow_period: int = 50, devup: float = 1, devdn: float = 1, fast_matype: int = 0, slow_matype: int = 0,
                    source_type: str = "close",
                    sequential: bool = False) -> MAB:
    """
    Moving Average Bands

    :param candles: np.ndarray
    :param fast_period: int - default: 10
    :param slow_period: int - default: 50
    :param devup: float - default: 1
    :param devdn: float - default: 1
    :param fast_matype: int - default: 0
    :param slow_matype: int - default: 0
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: MAB(upperband, middleband, lowerband)
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    fastEma = ma(source, period=fast_period, matype=fast_matype, sequential=True)
    slowEma = ma(source, period=slow_period, matype=slow_matype, sequential=True)
    sqAvg = talib.SUM(np.power(fastEma - slowEma, 2), fast_period) / fast_period
    dev = np.sqrt(sqAvg)

    middlebands = fastEma
    upperbands = slowEma + devup * dev
    lowerbands = slowEma - devdn * dev


    if sequential:
        return MAB(upperbands, middlebands, lowerbands)
    else:
        return MAB(upperbands[-1], middlebands[-1], lowerbands[-1])
