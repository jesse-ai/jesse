from collections import namedtuple

import numpy as np
import talib

VWMACD = namedtuple('VWMACD', ['macd', 'signal', 'hist'])


def vwmacd(candles: np.ndarray, fastperiod=12, slowperiod=26, signalperiod=9, sequential=False) -> VWMACD:
    """
    VWMACD - Volume Weighted Moving Average Convergence/Divergence

    :param candles: np.ndarray
    :param fastperiod: int - default: 12
    :param slow_period: int - default: 26
    :param signal_period: int - default: 9
    :param sequential: bool - default: False

    :return: VWMACD(macd, signal, hist)
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    vwma_slow = talib.SMA(candles[:, 2] * candles[:, 5], slowperiod) / talib.SMA(candles[:, 5], slowperiod)
    vwma_fast = talib.SMA(candles[:, 2] * candles[:, 5], fastperiod) / talib.SMA(candles[:, 5], fastperiod)
    vwmacd = vwma_fast - vwma_slow
    signal = talib.EMA(vwmacd, signalperiod)
    hist = vwmacd - signal

    if sequential:
        return VWMACD(vwmacd, signal, hist)
    else:
        return VWMACD(vwmacd[-1], signal[-1], hist[-1])
