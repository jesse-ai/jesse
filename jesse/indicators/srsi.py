import numpy as np
import talib
import tulipy as ti
from jesse.helpers import get_candle_source

from collections import namedtuple

StochasticRSI = namedtuple('StochasticRSI', ['k', 'd'])


def srsi(candles: np.ndarray, period=14, source_type="close", sequential=False) -> StochasticRSI:
    """
    Stochastic RSI

    :param candles: np.ndarray
    :param period: int - default: 14
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: StochasticRSI
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    rsi_np = talib.RSI(source, timeperiod=period)
    rsi_np = rsi_np[np.logical_not(np.isnan(rsi_np))]
    fast_k, fast_d = ti.stoch(rsi_np, rsi_np, rsi_np, 14, 3, 3)

    if sequential:
        fast_k = np.concatenate((np.full((candles.shape[0]-fast_k.shape[0]), np.nan), fast_k), axis=0)
        fast_d = np.concatenate((np.full((candles.shape[0]-fast_d.shape[0]), np.nan), fast_d), axis=0)
        return StochasticRSI(fast_k, fast_d)
    else:
        return StochasticRSI(fast_k[-1], fast_d[-1])
