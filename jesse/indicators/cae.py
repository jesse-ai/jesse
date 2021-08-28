import numpy as np
from typing import Union
import jesse.indicators as ta

try:
    from numba import njit
except ImportError:
    njit = lambda a: a

from jesse.helpers import get_candle_source, slice_candles


def cae(candles: np.ndarray, length: int = 14, source_type="close", sequential=False) -> \
        Union[float, np.ndarray]:
    """
    Chop and explode by fhenry0331 - https://www.tradingview.com/script/5X5mhe3z-Chop-and-explode/
    The purpose of this script is to decipher chop zones from runs/movement/explosion

    The chop is RSI movement between 40 and 60
    tight chop is RSI movement between 45 and 55. There should be an explosion after RSI breaks through 60 (long) or
    40 (short). Tight chop bars are colored black, a series of black bars is tight consolidation and should explode imminently.
    The longer the chop the longer the explosion will go for. tighter the better.

    Loose chop (whip saw/yellow bars) will range between 40 and 60.
    the move begins with blue bars for long and purple bars for short.
    Couple it with your trading system to help stay out of chop and enter when there is movement. Use with "Simple Trender."

    :param candles: np.ndarray
    :param length: int - default: 14
    :param source_type: str - default: close
    :param sequential: bool - default: False
    :return: Union[float, np.ndarray]
    """

    if length < 1:
        raise ValueError('Bad parameters.')

    # Accept normal array too.
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    change = np.ediff1d(source)
    positives = np.copy(change)
    negatives = np.copy(change)

    positives[positives < 0] = 0
    negatives[negatives > 0] = 0

    up = ta.rma(positives, length, sequential=True)
    down = ta.rma(-negatives, length, sequential=True)

    rsi = rsi_fast(up, down)

    return rsi if sequential else rsi[-1]


@njit
def rsi_fast(up, down):
    out = np.full_like(up, np.nan)
    for i in range(up.size):

        if down[i] == 0:
            out[i] = 100
        elif up[i] == 0:
            out[i] = 0
        else:
            out[i] = 100 - (100 / (1 + up[i] / down[i]))

    return out
