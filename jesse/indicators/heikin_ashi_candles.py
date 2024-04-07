import numpy as np
from collections import namedtuple
from jesse.helpers import slice_candles

try:
    from numba import njit
except ImportError:
    njit = lambda a : a

HA = namedtuple('HA', ['open', 'close', 'high', 'low'])

def heikin_ashi_candles(candles: np.ndarray, sequential: bool = False) -> HA:
    """
    Heikin Ashi Candles
    :param candles: np.ndarray
    :param sequential: bool - default: False
    :return: float | np.ndarray
    """

    source = slice_candles(candles, sequential)
    # Just pick the OPEN,CLOSE,HIGH,LOW Columns from the candles
    open, close, high, low = ha_fast(source[:,[1,2,3,4]])

    if sequential:
        return HA(open, close, high, low)
    else:
        return HA(open[-1], close[-1], high[-1], low[-1])

@njit
def ha_fast(source):

    # index consts to facilitate reading the code
    OPEN = 0
    CLOSE = 1
    HIGH = 2
    LOW = 3

    # init array
    ha_candles = np.full_like(source, np.nan)
    for i in range(1,ha_candles.shape[0]):
        # https://www.investopedia.com/trading/heikin-ashi-better-candlestick/
        #
        ha_candles[i][OPEN] = (source[i-1][OPEN]+source[i-1][CLOSE])/2
        ha_candles[i][CLOSE] = (source[i][OPEN]+source[i][CLOSE]+source[i][HIGH]+source[i][LOW])/4
        # Using builtins Python min,max and not numpy one since we get this Error:
        # No implementation of function Function() found for signature:
        # Still fast since numba supports it 
        ha_candles[i][HIGH] = max([source[i][HIGH], ha_candles[i][OPEN], ha_candles[i][CLOSE]])
        ha_candles[i][LOW] = min([source[i][LOW], ha_candles[i][OPEN], ha_candles[i][CLOSE]])

    return ha_candles[:,OPEN], ha_candles[:,CLOSE], ha_candles[:,HIGH], ha_candles[:,LOW]