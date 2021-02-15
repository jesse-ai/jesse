from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_candle_source

RSMK = namedtuple('RSMK', ['indicator', 'signal'])


def rsmk(candles: np.ndarray, candles_compare: np.ndarray, lookback: int = 90, period: int = 3, signal_period: int = 20,
         matype: int = 1,
         signal_matype: int = 1, source_type: str = "close", sequential: bool = False) -> RSMK:
    """
    RSMK - Relative Strength

    :param candles: np.ndarray
    :param candles_compare: np.ndarray
    :param period: int - default: 3
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]
        candles_compare = candles_compare[-240:]

    source = get_candle_source(candles, source_type=source_type)
    source_compare = get_candle_source(candles_compare, source_type=source_type)

    a = np.log(source / source_compare)
    b = talib.MOM(a, timeperiod=lookback)

    res = talib.MA(b, timeperiod=period, matype=matype) * 100

    signal = talib.MA(res, timeperiod=signal_period, matype=signal_matype)

    if sequential:
        return RSMK(res, signal)
    else:
        return RSMK(None if np.isnan(res[-1]) else res[-1], None if np.isnan(signal[-1]) else signal[-1])
