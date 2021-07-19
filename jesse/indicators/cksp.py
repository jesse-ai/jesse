from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import slice_candles


CKSP = namedtuple('CKSP', ['long', 'short'])

def cksp(candles: np.ndarray, p: int = 10, x: float = 1.0,  q: int = 9, sequential: bool = False) -> CKSP:
    """
    Chande Kroll Stop (CKSP)

    :param candles: np.ndarray
    :param p: int - default: 10
    :param x: float - default: 1.0
    :param q: int - default: 9
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    candles_close = candles[:, 2]
    candles_high = candles[:, 3]
    candles_low = candles[:, 4]

    atr = talib.ATR(candles_high, candles_low, candles_close, timeperiod=p)

    LS0 = talib.MAX(candles_high, q) - x * atr
    LS = talib.MAX(LS0, q)

    SS0 = talib.MIN(candles_low, q) + x * atr
    SS = talib.MIN(SS0, q)

    if sequential:
        return CKSP(LS, SS)
    else:
        return CKSP(LS[-1], SS[-1])

