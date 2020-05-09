import numpy as np
import talib
import tulipy as ti

from collections import namedtuple

StochasticRSI = namedtuple('StochasticRSI', ['k', 'd'])


def srsi(candles: np.ndarray, period=14, sequential=False) -> StochasticRSI:
    """
    Stochastic RSI

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default=False

    :return: StochasticRSI
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    rsi_np = talib.RSI(candles[:, 2], timeperiod=period)
    rsi_np = rsi_np[np.logical_not(np.isnan(rsi_np))]
    fast_k, fast_d = ti.stoch(rsi_np, rsi_np, rsi_np, 14, 3, 3)

    if sequential:
        fast_k = np.concatenate((np.full((17 + period), np.nan), fast_k), axis=0)
        fast_d = np.concatenate((np.full((17 + period), np.nan), fast_d), axis=0)
        return StochasticRSI(fast_k, fast_d)
    else:
        return StochasticRSI(fast_k[-1], fast_d[-1])
