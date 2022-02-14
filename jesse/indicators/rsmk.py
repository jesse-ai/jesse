from collections import namedtuple

import numpy as np
import talib
from jesse.indicators.ma import ma

from jesse.helpers import get_candle_source

RSMK = namedtuple('RSMK', ['indicator', 'signal'])


def rsmk(candles: np.ndarray, candles_compare: np.ndarray, lookback: int = 90, period: int = 3, signal_period: int = 20,
         matype: int = 1,
         signal_matype: int = 1, source_type: str = "close", sequential: bool = False) -> RSMK:
    """
    RSMK - Relative Strength

    :param candles: np.ndarray
    :param candles_compare: np.ndarray
    :param lookback: int - default: 90
    :param period: int - default: 3
    :param signal_period: int - default: 20
    :param matype: int - default: 1
    :param signal_matype: int - default: 1
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if not sequential and candles.shape[0] > 240:
        candles = candles[-240:]
        candles_compare = candles_compare[-240:]

    source = get_candle_source(candles, source_type=source_type)
    source_compare = get_candle_source(candles_compare, source_type=source_type)

    a = np.log(source / source_compare)
    b = talib.MOM(a, timeperiod=lookback)

    res = ma(b, period=period, matype=matype, sequential=True) * 100

    signal = ma(res, period=signal_period, matype=signal_matype, sequential=True)

    if sequential:
        return RSMK(res, signal)
    else:
        return RSMK(res[-1], signal[-1])

