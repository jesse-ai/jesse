from collections import namedtuple

import numpy as np
import talib
import tulipy as ti

from jesse.helpers import get_candle_source, same_length, slice_candles

StochasticRSI = namedtuple('StochasticRSI', ['k', 'd'])


def srsi(candles: np.ndarray, period: int = 14, period_stoch: int = 14, k: int = 3, d: int = 3,
         source_type: str = "close", sequential: bool = False) -> StochasticRSI:
    """
    Stochastic RSI

    :param candles: np.ndarray
    :param period: int - default: 14 - RSI Length
    :param period_stoch: int - default: 14 - Stochastic Length
    :param k: int - default: 3
    :param d: int - default: 3
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: StochasticRSI(k, d)
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    rsi_np = talib.RSI(source, timeperiod=period)
    rsi_np = rsi_np[np.logical_not(np.isnan(rsi_np))]
    fast_k, fast_d = ti.stoch(rsi_np, rsi_np, rsi_np, period_stoch, k, d)

    if sequential:
        fast_k = same_length(candles, fast_k)
        fast_d = same_length(candles, fast_d)
        return StochasticRSI(fast_k, fast_d)
    else:
        return StochasticRSI(fast_k[-1], fast_d[-1])
