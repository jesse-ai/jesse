from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import slice_candles

VWMACD = namedtuple('VWMACD', ['macd', 'signal', 'hist'])


def vwmacd(candles: np.ndarray, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9,
           sequential: bool = False) -> VWMACD:
    """
    VWMACD - Volume Weighted Moving Average Convergence/Divergence

    :param candles: np.ndarray
    :param fast_period: int - default: 12
    :param slow_period: int - default: 26
    :param signal_period: int - default: 9
    :param sequential: bool - default: False

    :return: VWMACD(macd, signal, hist)
    """
    candles = slice_candles(candles, sequential)

    vwma_slow = talib.SMA(candles[:, 2] * candles[:, 5], slow_period) / talib.SMA(candles[:, 5], slow_period)
    vwma_fast = talib.SMA(candles[:, 2] * candles[:, 5], fast_period) / talib.SMA(candles[:, 5], fast_period)
    vwmacd = vwma_fast - vwma_slow
    signal = talib.EMA(vwmacd, signal_period)
    hist = vwmacd - signal

    if sequential:
        return VWMACD(vwmacd, signal, hist)
    else:
        return VWMACD(vwmacd[-1], signal[-1], hist[-1])
